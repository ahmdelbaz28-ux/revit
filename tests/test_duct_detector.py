"""
tests/test_duct_detector.py
============================
Comprehensive test suite for:
  fireai/core/duct_detector.py

NFPA 72-2022 §17.7.5 Duct Detector Placement.

SAFETY CRITICAL: Missing duct smoke detectors on air-handling units
>2000 CFM can allow smoke to circulate throughout a building via
the HVAC system — a life-safety hazard.

NFPA 72 References:
  §17.7.5.1 — Detectors required for AHU >2000 CFM
  §17.7.5.3 — Detector location within duct
NFPA 90A References:
  §6.4.2.2 — Maximum 10 ft (3.05m) spacing between duct detectors
UL 268A:
  Max velocity 4000 FPM, min velocity 100 FPM for reliable detection
"""

from __future__ import annotations

import math

import pytest

from fireai.core.duct_detector import (
    NFPA_DUCT_MAX_SPACING_M,
    UL268A_MAX_VELOCITY_FPM,
    UL268A_MIN_VELOCITY_FPM,
    DuctSpec,
    analyse_duct,
    analyse_ducts,
    total_duct_detectors,
)

# ─────────────────────────────────────────────────────────────────────────────
# DuctSpec — Construction and Validation
# ─────────────────────────────────────────────────────────────────────────────


class TestDuctSpec:
    """DuctSpec dataclass construction and input validation."""

    def test_basic_construction(self):
        """Basic DuctSpec creation."""
        duct = DuctSpec(
            duct_id="D1",
            length_m=10.0,
            width_m=0.5,
            start_point=(0.0, 0.0),
            end_point=(10.0, 0.0),
        )
        assert duct.duct_id == "D1"
        assert duct.length_m == 10.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert duct.width_m == 0.5  # NOSONAR — S1244: import retained for re-export / API surface
        assert duct.duct_type == "supply"

    def test_default_values(self):
        """Default duct_type is supply, default points are (0,0)→(1,0)."""
        duct = DuctSpec(duct_id="D1", length_m=5.0, width_m=0.3)
        assert duct.duct_type == "supply"
        assert duct.start_point == (0.0, 0.0)
        assert duct.end_point == (1.0, 0.0)
        assert duct.airflow_cfm is None
        assert duct.height_m == 0.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_return_duct(self):
        """Return duct type."""
        duct = DuctSpec(duct_id="D1", length_m=5.0, width_m=0.3, duct_type="return")
        assert duct.duct_type == "return"

    def test_exhaust_duct(self):
        """Exhaust duct type."""
        duct = DuctSpec(duct_id="D1", length_m=5.0, width_m=0.3, duct_type="exhaust")
        assert duct.duct_type == "exhaust"

    def test_mixed_duct(self):
        """Mixed duct type."""
        duct = DuctSpec(duct_id="D1", length_m=5.0, width_m=0.3, duct_type="mixed")
        assert duct.duct_type == "mixed"

    def test_invalid_duct_type_raises(self):
        """V25 FIX: Invalid duct_type must raise ValueError."""
        with pytest.raises(ValueError, match="not a recognized"):
            DuctSpec(duct_id="D1", length_m=5.0, width_m=0.3, duct_type="suply")

    def test_duct_type_normalized(self):
        """V50 FIX: Duct type with spaces must be normalized."""
        duct = DuctSpec(duct_id="D1", length_m=5.0, width_m=0.3, duct_type=" supply ")
        assert duct.duct_type == "supply"

    def test_nan_length_raises(self):
        """V50 FIX: NaN length must raise ValueError."""
        with pytest.raises(ValueError, match="invalid"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            DuctSpec(duct_id="D1", length_m=float("nan"), width_m=0.3)

    def test_inf_length_raises(self):
        """Infinite length is not valid."""
        with pytest.raises(ValueError, match="invalid"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            DuctSpec(duct_id="D1", length_m=float("inf"), width_m=0.3)

    def test_negative_length_raises(self):
        """Negative length is not valid."""
        with pytest.raises(ValueError, match="invalid"):
            DuctSpec(duct_id="D1", length_m=-5.0, width_m=0.3)

    def test_nan_width_raises(self):
        """NaN width must raise ValueError."""
        with pytest.raises(ValueError, match="invalid"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            DuctSpec(duct_id="D1", length_m=5.0, width_m=float("nan"))

    def test_negative_width_raises(self):
        """Negative width is not valid."""
        with pytest.raises(ValueError, match="invalid"):
            DuctSpec(duct_id="D1", length_m=5.0, width_m=-0.3)

    def test_nan_airflow_cfm_raises(self):
        """NaN airflow_cfm must raise ValueError."""
        with pytest.raises(ValueError, match="invalid"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            DuctSpec(duct_id="D1", length_m=5.0, width_m=0.3, airflow_cfm=float("nan"))

    def test_negative_airflow_cfm_raises(self):
        """Negative airflow_cfm is not valid."""
        with pytest.raises(ValueError, match="invalid"):
            DuctSpec(duct_id="D1", length_m=5.0, width_m=0.3, airflow_cfm=-100.0)

    def test_none_airflow_cfm_is_valid(self):
        """None airflow_cfm is valid (unknown CFM — conservative)."""
        duct = DuctSpec(duct_id="D1", length_m=5.0, width_m=0.3, airflow_cfm=None)
        assert duct.airflow_cfm is None

    def test_zero_width_is_valid(self):
        """Zero width is valid (results in exemption)."""
        duct = DuctSpec(duct_id="D1", length_m=5.0, width_m=0.0)
        assert duct.width_m == 0.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_nan_height_raises(self):
        """NaN height_m is not valid."""
        with pytest.raises(ValueError, match="invalid"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            DuctSpec(duct_id="D1", length_m=5.0, width_m=0.3, height_m=float("nan"))

    def test_negative_height_raises(self):
        """Negative height_m is not valid."""
        with pytest.raises(ValueError, match="invalid"):
            DuctSpec(duct_id="D1", length_m=5.0, width_m=0.3, height_m=-0.5)


# ─────────────────────────────────────────────────────────────────────────────
# analyse_duct — Exemptions
# ─────────────────────────────────────────────────────────────────────────────


class TestDuctExemptions:
    """Duct detector exemption logic per NFPA 72 §17.7.5.1."""

    def test_zero_width_exempt(self):
        """Zero width duct is exempt (when CFM is known and ≤2000)."""
        # V68 FIX: Must provide known CFM ≤2000 to allow dimension exemption
        duct = DuctSpec(duct_id="D1", length_m=5.0, width_m=0.0, airflow_cfm=1000.0, duct_type="supply")
        result = analyse_duct(duct)
        assert result.exempt is True
        assert result.detector_count == 0

    def test_zero_length_exempt(self):
        """Zero length duct is exempt (when CFM is known and ≤2000)."""
        duct = DuctSpec(duct_id="D1", length_m=0.0, width_m=0.5, airflow_cfm=1000.0, duct_type="supply")
        result = analyse_duct(duct)
        assert result.exempt is True
        assert result.detector_count == 0

    def test_narrow_duct_exempt(self):
        """Duct narrower than minimum width (0.20m) is exempt."""
        # V68 FIX: Must provide known CFM ≤2000 to allow dimension exemption
        duct = DuctSpec(duct_id="D1", length_m=5.0, width_m=0.15, airflow_cfm=1000.0, duct_type="supply")
        result = analyse_duct(duct)
        assert result.exempt is True
        assert "width" in result.exemption_reason.lower()

    def test_short_duct_exempt(self):
        """Duct shorter than minimum length (1.0m) is exempt."""
        duct = DuctSpec(duct_id="D1", length_m=0.5, width_m=0.5, airflow_cfm=1000.0, duct_type="supply")
        result = analyse_duct(duct)
        assert result.exempt is True
        assert "length" in result.exemption_reason.lower()

    def test_exhaust_duct_exempt(self):
        """Exhaust ducts don't require detectors per §17.7.5.1."""
        duct = DuctSpec(duct_id="D1", length_m=10.0, width_m=0.5, duct_type="exhaust")
        result = analyse_duct(duct)
        assert result.exempt is True
        assert "exhaust" in result.exemption_reason.lower()

    def test_exhaust_duct_exempt_even_if_large(self):
        """Even large exhaust ducts are exempt."""
        duct = DuctSpec(
            duct_id="D1", length_m=20.0, width_m=1.0,
            duct_type="exhaust", airflow_cfm=5000.0,
        )
        result = analyse_duct(duct)
        assert result.exempt is True


# ─────────────────────────────────────────────────────────────────────────────
# analyse_duct — CFM Override (V68 FIX)
# ─────────────────────────────────────────────────────────────────────────────


class TestCFMOverride:
    """V68 FIX: CFM >2000 for supply/return overrides dimension exemptions."""

    def test_high_cfm_overrides_narrow_duct(self):
        """CFM >2000 supply duct — even if narrow, detector required."""
        duct = DuctSpec(
            duct_id="D1", length_m=5.0, width_m=0.15,
            airflow_cfm=3000.0, duct_type="supply",
        )
        result = analyse_duct(duct)
        assert result.exempt is False
        assert result.detector_count > 0

    def test_high_cfm_overrides_short_duct(self):
        """CFM >2000 supply duct — even if short, detector required."""
        duct = DuctSpec(
            duct_id="D1", length_m=0.5, width_m=0.5,
            airflow_cfm=3000.0, duct_type="supply",
        )
        result = analyse_duct(duct)
        assert result.exempt is False

    def test_high_cfm_return_duct(self):
        """CFM >2000 return duct — detector required."""
        duct = DuctSpec(
            duct_id="D1", length_m=5.0, width_m=0.5,
            airflow_cfm=5000.0, duct_type="return",
        )
        result = analyse_duct(duct)
        assert result.exempt is False

    def test_cfm_unknown_blocks_exemption(self):
        """V68 FIX: Unknown CFM for supply/return blocks dimension exemption."""
        # A narrow supply duct with unknown CFM — AHU could be >2000 CFM
        duct = DuctSpec(
            duct_id="D1", length_m=5.0, width_m=0.15,
            airflow_cfm=None, duct_type="supply",
        )
        result = analyse_duct(duct)
        assert result.exempt is False

    def test_cfm_unknown_return_blocks_exemption(self):
        """Unknown CFM for return duct also blocks exemption."""
        duct = DuctSpec(
            duct_id="D1", length_m=0.5, width_m=0.5,
            airflow_cfm=None, duct_type="return",
        )
        result = analyse_duct(duct)
        assert result.exempt is False

    def test_low_cfm_allows_exemption(self):
        """Known CFM ≤2000 allows dimension exemption."""
        duct = DuctSpec(
            duct_id="D1", length_m=0.5, width_m=0.5,
            airflow_cfm=1500.0, duct_type="supply",
        )
        result = analyse_duct(duct)
        assert result.exempt is True

    def test_cfm_exactly_at_threshold_not_overriding(self):
        """CFM = 2000 exactly → NOT overriding (> is required, not ≥)."""
        duct = DuctSpec(
            duct_id="D1", length_m=0.5, width_m=0.5,
            airflow_cfm=2000.0, duct_type="supply",
        )
        result = analyse_duct(duct)
        assert result.exempt is True  # Short duct exemption applies


# ─────────────────────────────────────────────────────────────────────────────
# analyse_duct — Detector Placement
# ─────────────────────────────────────────────────────────────────────────────


class TestDetectorPlacement:
    """Detector count and spacing calculations."""

    def test_short_duct_one_detector(self):
        """Duct ≤ 3.05m needs 1 detector."""
        duct = DuctSpec(
            duct_id="D1", length_m=3.0, width_m=0.5,
            start_point=(0, 0), end_point=(3, 0),
            duct_type="supply", airflow_cfm=3000.0,
        )
        result = analyse_duct(duct)
        assert result.detector_count == 1
        assert result.spacing_used_m <= NFPA_DUCT_MAX_SPACING_M + 0.01

    def test_medium_duct_multiple_detectors(self):
        """Duct = 10m needs ceil(10/3.05) = 4 detectors."""
        duct = DuctSpec(
            duct_id="D1", length_m=10.0, width_m=0.5,
            start_point=(0, 0), end_point=(10, 0),
            duct_type="supply", airflow_cfm=3000.0,
        )
        result = analyse_duct(duct)
        expected = math.ceil(10.0 / NFPA_DUCT_MAX_SPACING_M)
        assert result.detector_count == expected

    def test_detector_positions_along_centreline(self):
        """Detector positions should be along the duct centreline."""
        duct = DuctSpec(
            duct_id="D1", length_m=6.1, width_m=0.5,
            start_point=(0, 0), end_point=(6.1, 0),
            duct_type="supply", airflow_cfm=3000.0,
        )
        result = analyse_duct(duct)
        for det in result.detectors:
            assert 0 <= det.distance_from_start_m <= duct.length_m + 0.01

    def test_spacing_within_nfpa_limit(self):
        """Auto-calculated spacing must not exceed NFPA limit."""
        duct = DuctSpec(
            duct_id="D1", length_m=20.0, width_m=0.5,
            start_point=(0, 0), end_point=(20, 0),
            duct_type="supply", airflow_cfm=5000.0,
        )
        result = analyse_duct(duct)
        assert result.spacing_used_m <= NFPA_DUCT_MAX_SPACING_M + 0.01

    def test_detector_positions_x_coordinates(self):
        """Detector x-coordinates should interpolate between start and end."""
        duct = DuctSpec(
            duct_id="D1", length_m=10.0, width_m=0.5,
            start_point=(0, 0), end_point=(10, 0),
            duct_type="supply", airflow_cfm=3000.0,
        )
        result = analyse_duct(duct)
        for det in result.detectors:
            # For a horizontal duct, x should be between start and end
            assert 0.0 <= det.x <= 10.0 + 0.01

    def test_detector_index_is_one_based(self):
        """Detector indices must be 1-based."""
        duct = DuctSpec(
            duct_id="D1", length_m=10.0, width_m=0.5,
            start_point=(0, 0), end_point=(10, 0),
            duct_type="supply", airflow_cfm=3000.0,
        )
        result = analyse_duct(duct)
        for i, det in enumerate(result.detectors):
            assert det.index == i + 1

    def test_duct_id_propagated_to_detectors(self):
        """Detector duct_id must match the source duct."""
        duct = DuctSpec(
            duct_id="AHU-1-SUPPLY", length_m=10.0, width_m=0.5,
            start_point=(0, 0), end_point=(10, 0),
            duct_type="supply", airflow_cfm=3000.0,
        )
        result = analyse_duct(duct)
        for det in result.detectors:
            assert det.duct_id == "AHU-1-SUPPLY"

    def test_nfpa_ref_in_detectors(self):
        """Each detector position must cite NFPA 72 §17.7.5."""
        duct = DuctSpec(
            duct_id="D1", length_m=10.0, width_m=0.5,
            duct_type="supply", airflow_cfm=3000.0,
        )
        result = analyse_duct(duct)
        for det in result.detectors:
            assert "17.7.5" in det.nfpa_ref
            assert "6.4.2.2" in det.spacing_ref  # NOSONAR - python:S1313


# ─────────────────────────────────────────────────────────────────────────────
# analyse_duct — Velocity Blindness (UL 268A)
# ─────────────────────────────────────────────────────────────────────────────


class TestVelocityBlindness:
    """UL 268A velocity range checks for duct smoke detection."""

    def test_high_velocity_blindness(self):
        """Velocity > 4000 FPM → velocity_blindness = True."""
        # Create a small duct with very high CFM
        # Round duct: area = π × (0.25)² = 0.196 m² → 2.11 ft²
        # 10000 CFM / 2.11 ft² = 4739 FPM > 4000
        duct = DuctSpec(
            duct_id="D1", length_m=10.0, width_m=0.5,
            duct_type="supply", airflow_cfm=10000.0,
        )
        result = analyse_duct(duct)
        assert result.velocity_blindness is True
        assert result.velocity_fpm > UL268A_MAX_VELOCITY_FPM

    def test_normal_velocity_no_blindness(self):
        """Velocity in normal range → no blindness."""
        duct = DuctSpec(
            duct_id="D1", length_m=10.0, width_m=0.5,
            duct_type="supply", airflow_cfm=2000.0,
        )
        result = analyse_duct(duct)
        assert result.velocity_blindness is False

    def test_low_velocity_blindness(self):
        """V20.2 FIX: Velocity < 100 FPM → stagnation blindness."""
        # Very low CFM for a large duct
        # Round duct: area = π × (1.0)² = 3.14 m² → 33.8 ft²
        # 500 CFM / 33.8 ft² = 14.8 FPM < 100
        duct = DuctSpec(
            duct_id="D1", length_m=10.0, width_m=2.0,
            duct_type="supply", airflow_cfm=500.0,
        )
        result = analyse_duct(duct)
        assert result.velocity_blindness is True
        assert result.velocity_fpm < UL268A_MIN_VELOCITY_FPM

    def test_rectangular_duct_velocity(self):
        """Rectangular duct velocity calculation uses width × height."""
        duct = DuctSpec(
            duct_id="D1", length_m=10.0, width_m=1.0, height_m=0.5,
            duct_type="supply", airflow_cfm=3000.0,
        )
        result = analyse_duct(duct)
        # Area = 1.0 × 0.5 = 0.5 m² → 5.38 ft²
        # 3000 / 5.38 ≈ 557 FPM → no blindness
        assert result.velocity_blindness is False
        assert result.velocity_fpm > 0

    def test_no_cfm_zero_velocity(self):
        """No CFM → velocity = 0, no blindness."""
        duct = DuctSpec(
            duct_id="D1", length_m=10.0, width_m=0.5,
            duct_type="supply", airflow_cfm=None,
        )
        result = analyse_duct(duct)
        assert result.velocity_fpm == 0.0  # NOSONAR — S1244: import retained for re-export / API surface
        assert result.velocity_blindness is False

    def test_detectors_functional_when_no_blindness(self):
        """V51 FIX: detectors_functional = True when no velocity issue."""
        duct = DuctSpec(
            duct_id="D1", length_m=10.0, width_m=0.5,
            duct_type="supply", airflow_cfm=3000.0,
        )
        result = analyse_duct(duct)
        assert result.detectors_functional is True

    def test_detectors_non_functional_when_blindness(self):
        """V51 FIX: detectors_functional = False when velocity blindness."""
        duct = DuctSpec(
            duct_id="D1", length_m=10.0, width_m=0.5,
            duct_type="supply", airflow_cfm=10000.0,
        )
        result = analyse_duct(duct)
        assert result.velocity_blindness is True
        assert result.detectors_functional is False


# ─────────────────────────────────────────────────────────────────────────────
# analyse_duct — HVAC Shutdown (V20.2 FIX)
# ─────────────────────────────────────────────────────────────────────────────


class TestHVACShutdown:
    """V20.2 FIX: HVAC shutdown flag per NFPA 72 §21.7.1."""

    def test_supply_high_cfm_requires_shutdown(self):
        """Supply duct >2000 CFM requires HVAC shutdown."""
        duct = DuctSpec(
            duct_id="D1", length_m=10.0, width_m=0.5,
            duct_type="supply", airflow_cfm=5000.0,
        )
        result = analyse_duct(duct)
        assert result.hvac_shutdown_required is True
        assert "21.7.1" in result.hvac_shutdown_ref

    def test_supply_unknown_cfm_requires_shutdown(self):
        """Supply duct with unknown CFM requires shutdown (conservative)."""
        duct = DuctSpec(
            duct_id="D1", length_m=10.0, width_m=0.5,
            duct_type="supply", airflow_cfm=None,
        )
        result = analyse_duct(duct)
        assert result.hvac_shutdown_required is True

    def test_supply_low_cfm_no_shutdown(self):
        """Supply duct ≤2000 CFM does NOT require shutdown."""
        duct = DuctSpec(
            duct_id="D1", length_m=10.0, width_m=0.5,
            duct_type="supply", airflow_cfm=1000.0,
        )
        result = analyse_duct(duct)
        assert result.hvac_shutdown_required is False

    def test_exhaust_no_shutdown(self):
        """Exhaust ducts don't require HVAC shutdown."""
        duct = DuctSpec(
            duct_id="D1", length_m=10.0, width_m=0.5,
            duct_type="exhaust", airflow_cfm=5000.0,
        )
        result = analyse_duct(duct)
        assert result.hvac_shutdown_required is False


# ─────────────────────────────────────────────────────────────────────────────
# analyse_duct — Warnings
# ─────────────────────────────────────────────────────────────────────────────


class TestDuctWarnings:
    """Warning generation in duct analysis."""

    def test_length_mismatch_warning(self):
        """When length_m differs from geometric distance → warning."""
        duct = DuctSpec(
            duct_id="D1", length_m=15.0, width_m=0.5,
            start_point=(0, 0), end_point=(5, 0),
            duct_type="supply", airflow_cfm=3000.0,
        )
        result = analyse_duct(duct)
        assert any("differs" in w.lower() for w in result.warnings)

    def test_low_cfm_warning(self):
        """CFM ≤2000 for supply/return → verify warning."""
        duct = DuctSpec(
            duct_id="D1", length_m=10.0, width_m=0.5,
            duct_type="supply", airflow_cfm=1500.0,
        )
        result = analyse_duct(duct)
        assert any("CFM" in w for w in result.warnings)

    def test_velocity_blindness_warning(self):
        """High velocity → warning about UL 268A limit."""
        duct = DuctSpec(
            duct_id="D1", length_m=10.0, width_m=0.5,
            duct_type="supply", airflow_cfm=10000.0,
        )
        result = analyse_duct(duct)
        assert any("UL 268A" in w for w in result.warnings)

    def test_no_warnings_for_perfect_duct(self):
        """Well-specified duct with matching geometry has no spurious warnings."""
        duct = DuctSpec(
            duct_id="D1", length_m=10.0, width_m=0.5,
            start_point=(0, 0), end_point=(10, 0),
            duct_type="supply", airflow_cfm=3000.0,
        )
        result = analyse_duct(duct)
        # Should not have length mismatch warnings
        mismatch_warns = [w for w in result.warnings if "differs" in w.lower()]
        assert len(mismatch_warns) == 0


# analyse_ducts and total_duct_detectors  # NOSONAR - python:S125
# ─────────────────────────────────────────────────────────────────────────────


class TestBatchAnalysis:
    """Batch analysis functions."""

    def test_analyse_ducts_multiple(self):
        """analyse_ducts returns one result per duct."""
        ducts = [
            DuctSpec(duct_id="D1", length_m=10.0, width_m=0.5, airflow_cfm=3000.0, duct_type="supply"),
            DuctSpec(duct_id="D2", length_m=5.0, width_m=0.3, airflow_cfm=2000.0, duct_type="return"),
        ]
        results = analyse_ducts(ducts)
        assert len(results) == 2
        assert results[0].duct_id == "D1"
        assert results[1].duct_id == "D2"

    def test_analyse_ducts_empty_list(self):
        """Empty duct list returns empty results."""
        results = analyse_ducts([])
        assert len(results) == 0

    def test_total_duct_detectors(self):
        """total_duct_detectors sums detector counts correctly."""
        ducts = [
            DuctSpec(duct_id="D1", length_m=10.0, width_m=0.5, airflow_cfm=3000.0, duct_type="supply"),
            DuctSpec(duct_id="D2", length_m=6.0, width_m=0.5, airflow_cfm=3000.0, duct_type="return"),
        ]
        results = analyse_ducts(ducts)
        total = total_duct_detectors(results)
        assert total == sum(r.detector_count for r in results)

    def test_total_duct_detectors_empty(self):
        """Zero results → zero detectors."""
        assert total_duct_detectors([]) == 0


# ─────────────────────────────────────────────────────────────────────────────
# DuctAnalysisResult — NFPA References
# ─────────────────────────────────────────────────────────────────────────────


class TestNFPAReferences:
    """NFPA section references in analysis results."""

    def test_result_has_nfpa_ref(self):
        """DuctAnalysisResult must include NFPA reference."""
        duct = DuctSpec(
            duct_id="D1", length_m=10.0, width_m=0.5,
            duct_type="supply", airflow_cfm=3000.0,
        )
        result = analyse_duct(duct)
        assert "17.7.5" in result.nfpa_ref

    def test_result_has_spacing_ref(self):
        """DuctAnalysisResult must include spacing reference."""
        duct = DuctSpec(
            duct_id="D1", length_m=10.0, width_m=0.5,
            duct_type="supply", airflow_cfm=3000.0,
        )
        result = analyse_duct(duct)
        assert "6.4.2.2" in result.spacing_ref  # NOSONAR - python:S1313


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
