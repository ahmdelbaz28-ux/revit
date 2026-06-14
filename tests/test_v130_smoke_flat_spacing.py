"""
V130 CRITICAL FIX Verification — Smoke Detector Flat Spacing
=============================================================

Tests that smoke detector spacing is FLAT 9.1m per NFPA 72-2022 §17.7.3.2.3
with NO height-based reduction. The 1%/ft reduction applies to HEAT detectors
ONLY per Table 17.6.3.5.1.

Previous code incorrectly applied heat detector reduction to smoke detectors,
causing up to 65% over-densification at high ceilings.
"""

import pytest
import math


# ============================================================================
# Test 1: Canonical SSoT constants — smoke spacing is flat 9.1m
# ============================================================================

class TestSmokeFlatSpacingConstants:
    """Verify fireai/constants/nfpa72.py has flat 9.1m for smoke."""

    def test_smoke_max_spacing_is_9_1(self):
        """SMOKE_MAX_SPACING_M must be 9.1 per §17.7.3.2.3."""
        from fireai.constants.nfpa72 import SMOKE_MAX_SPACING_M
        assert SMOKE_MAX_SPACING_M == 9.1, (
            f"SMOKE_MAX_SPACING_M = {SMOKE_MAX_SPACING_M}, expected 9.1"
        )

    def test_smoke_height_spacing_table_all_9_1(self):
        """Every entry in SMOKE_HEIGHT_SPACING_TABLE must be 9.1m."""
        from fireai.constants.nfpa72 import SMOKE_HEIGHT_SPACING_TABLE
        for h_max, spacing in SMOKE_HEIGHT_SPACING_TABLE:
            assert spacing == 9.1, (
                f"At h<={h_max}m, smoke spacing = {spacing}m, expected 9.1m. "
                f"NFPA 72 §17.7.3.2.3 requires flat 9.1m at ALL heights."
            )

    def test_combined_table_smoke_column_all_9_1(self):
        """Smoke column in COMBINED_HEIGHT_SPACING_TABLE must be 9.1m."""
        from fireai.constants.nfpa72 import COMBINED_HEIGHT_SPACING_TABLE
        for h_max, smoke_spacing, heat_spacing in COMBINED_HEIGHT_SPACING_TABLE:
            assert smoke_spacing == 9.1, (
                f"At h<={h_max}m, smoke spacing = {smoke_spacing}m, expected 9.1m. "
                f"Combined table must reflect flat spacing per §17.7.3.2.3."
            )

    def test_combined_table_heat_column_is_reduced(self):
        """Heat column in COMBINED_HEIGHT_SPACING_TABLE must have reduction."""
        from fireai.constants.nfpa72 import COMBINED_HEIGHT_SPACING_TABLE
        # At h<=3.0m: heat = 6.10m (no reduction)
        assert COMBINED_HEIGHT_SPACING_TABLE[0][2] == 6.10
        # At h<=12.2m: heat = 3.70m (reduced per Table 17.6.3.5.1)
        assert COMBINED_HEIGHT_SPACING_TABLE[-1][2] == 3.70
        # Verify reduction is progressive (decreasing)
        heat_values = [heat for _, _, heat in COMBINED_HEIGHT_SPACING_TABLE]
        for i in range(1, len(heat_values)):
            assert heat_values[i] <= heat_values[i-1], (
                f"Heat spacing should decrease with height: "
                f"{heat_values[i]} > {heat_values[i-1]}"
            )

    def test_smoke_spacing_fallback_is_9_1(self):
        """SMOKE_SPACING_FALLBACK_M must be 9.1m (flat per §17.7.3.2.3)."""
        from fireai.constants.nfpa72 import SMOKE_SPACING_FALLBACK_M
        assert SMOKE_SPACING_FALLBACK_M == 9.1, (
            f"SMOKE_SPACING_FALLBACK_M = {SMOKE_SPACING_FALLBACK_M}, expected 9.1m. "
            f"No height-based reduction for smoke detectors."
        )

    def test_heat_spacing_fallback_is_3_5(self):
        """HEAT_SPACING_FALLBACK_M must remain 3.50m (conservative extrapolation)."""
        from fireai.constants.nfpa72 import HEAT_SPACING_FALLBACK_M
        assert HEAT_SPACING_FALLBACK_M == 3.50

    def test_smoke_coverage_radius(self):
        """Smoke coverage radius = 0.7 × 9.1 = 6.37m."""
        from fireai.constants.nfpa72 import SMOKE_COVERAGE_RADIUS_M
        assert SMOKE_COVERAGE_RADIUS_M == 6.37


# ============================================================================
# Test 2: qomn_kernel — compute_smoke_detector_spacing returns flat 9.1m
# ============================================================================

class TestQomnKernelSmokeFlatSpacing:
    """Verify qomn_kernel returns flat 9.1m smoke spacing at all heights."""

    @pytest.mark.parametrize("height", [
        2.0,    # Low ceiling
        3.0,    # Standard ceiling (10 ft)
        4.6,    # Medium ceiling (~15 ft)
        6.096,  # Practical ceiling limit (20 ft)
        7.6,    # High ceiling (~25 ft)
        9.1,    # 30 ft ceiling
        10.7,   # ~35 ft ceiling
        12.2,   # 40 ft ceiling (table max)
        15.0,   # Above table, below hard limit
        18.0,   # Near hard limit (60 ft)
    ])
    def test_smoke_spacing_flat_at_all_heights(self, height):
        """Smoke detector spacing must be 9.1m at ALL valid ceiling heights."""
        from fireai.core.qomn_kernel import compute_smoke_detector_spacing
        result = compute_smoke_detector_spacing(height)
        assert result["listed_spacing_m"] == pytest.approx(9.1, abs=0.01), (
            f"At h={height}m, spacing = {result['listed_spacing_m']}m, "
            f"expected 9.1m (flat per §17.7.3.2.3)"
        )

    @pytest.mark.parametrize("height", [
        2.0, 3.0, 6.096, 9.1, 12.2, 18.0,
    ])
    def test_smoke_coverage_radius_at_all_heights(self, height):
        """Coverage radius must be 0.7 × 9.1 = 6.37m at all heights."""
        from fireai.core.qomn_kernel import compute_smoke_detector_spacing
        result = compute_smoke_detector_spacing(height)
        assert result["coverage_radius_m"] == pytest.approx(6.37, abs=0.01), (
            f"At h={height}m, radius = {result['coverage_radius_m']}m, "
            f"expected 6.37m (0.7 × 9.1)"
        )

    def test_high_ceiling_stratification_advisory(self):
        """Heights above 6.096m should include stratification advisory."""
        from fireai.core.qomn_kernel import compute_smoke_detector_spacing
        # Above 20ft — advisory should be present
        result = compute_smoke_detector_spacing(8.0)
        assert "audit_notice" in result, "Stratification advisory missing for h>6.096m"
        assert "stratification" in result["audit_notice"].lower() or "17.7.1.11" in result["audit_notice"]
        assert "9.1m" in result["audit_notice"], "Advisory must confirm 9.1m flat spacing"

    def test_low_ceiling_no_advisory(self):
        """Heights at/below 6.096m should NOT have stratification advisory."""
        from fireai.core.qomn_kernel import compute_smoke_detector_spacing
        result = compute_smoke_detector_spacing(3.0)
        assert "audit_notice" not in result, (
            "Stratification advisory should not appear at h<=6.096m"
        )

    def test_nfpa_section_ref_correct(self):
        """NFPA section reference must cite §17.7.3.2.3."""
        from fireai.core.qomn_kernel import compute_smoke_detector_spacing
        result = compute_smoke_detector_spacing(3.0)
        assert "17.7.3.2.3" in result["nfpa_section"], (
            f"NFPA section should cite §17.7.3.2.3, got: {result['nfpa_section']}"
        )

    def test_table_row_says_flat_spacing(self):
        """table_row_used must state flat spacing per §17.7.3.2.3."""
        from fireai.core.qomn_kernel import compute_smoke_detector_spacing
        result = compute_smoke_detector_spacing(5.0)
        assert "flat" in result["table_row_used"].lower() or "17.7.3.2.3" in result["table_row_used"], (
            f"table_row_used should mention flat spacing: {result['table_row_used']}"
        )


# ============================================================================
# Test 3: nfpa72_calculations — calculate_coverage_radius_from_height
# ============================================================================

class TestCoverageRadiusFromHeightSmoke:
    """Verify calculate_coverage_radius_from_height returns flat 9.1m for smoke."""

    @pytest.mark.parametrize("height", [
        2.0, 3.0, 4.6, 6.096, 9.1, 12.2,
    ])
    def test_smoke_spacing_flat_in_table_range(self, height):
        """Smoke spacing must be 9.1m for all heights in table range."""
        from fireai.core.nfpa72_calculations import calculate_coverage_radius_from_height
        spec = calculate_coverage_radius_from_height(height, "smoke")
        assert spec.spacing_max == pytest.approx(9.1, abs=0.01), (
            f"At h={height}m, smoke spacing_max = {spec.spacing_max}m, expected 9.1m"
        )

    @pytest.mark.parametrize("height", [
        2.0, 3.0, 4.6, 6.096, 9.1, 12.2,
    ])
    def test_smoke_radius_flat_in_table_range(self, height):
        """Smoke coverage radius must be 6.37m for all heights in table range."""
        from fireai.core.nfpa72_calculations import calculate_coverage_radius_from_height
        spec = calculate_coverage_radius_from_height(height, "smoke")
        assert spec.radius == pytest.approx(6.37, abs=0.01), (
            f"At h={height}m, smoke radius = {spec.radius}m, expected 6.37m"
        )

    def test_smoke_spacing_beyond_table(self):
        """Smoke spacing beyond 12.2m must still be 9.1m (flat per §17.7.3.2.3)."""
        from fireai.core.nfpa72_calculations import calculate_coverage_radius_from_height
        spec = calculate_coverage_radius_from_height(14.0, "smoke")
        assert spec.spacing_max == pytest.approx(9.1, abs=0.01), (
            f"Smoke spacing at h=14.0m = {spec.spacing_max}m, expected 9.1m"
        )

    @pytest.mark.parametrize("height", [3.0, 6.0, 9.0, 12.2])
    def test_heat_spacing_decreases_with_height(self, height):
        """Heat detector spacing must decrease with height per Table 17.6.3.5.1."""
        from fireai.core.nfpa72_calculations import calculate_coverage_radius_from_height
        spec = calculate_coverage_radius_from_height(height, "heat")
        # Just verify heat spacing is less than the max (6.1m)
        assert spec.spacing_max <= 6.10, (
            f"Heat spacing at h={height}m = {spec.spacing_max}m, should be <= 6.10m"
        )

    def test_heat_at_3m_is_6_1(self):
        """Heat detector at h<=3.0m must be 6.1m (20 ft listed spacing)."""
        from fireai.core.nfpa72_calculations import calculate_coverage_radius_from_height
        spec = calculate_coverage_radius_from_height(3.0, "heat")
        assert spec.spacing_max == pytest.approx(6.10, abs=0.01)


# ============================================================================
# Test 4: nfpa72_technology_dispatcher — smoke spacing is flat
# ============================================================================

class TestTechnologyDispatcherSmokeFlat:
    """Verify technology dispatcher returns flat 9.1m for point smoke."""

    @pytest.mark.parametrize("height", [
        3.0, 6.0, 9.0, 10.5, 12.0,
    ])
    def test_point_smoke_spacing_flat(self, height):
        """Point smoke detector spacing must be 9.1m at all heights within table."""
        from fireai.core.nfpa72_technology_dispatcher import (
            EliteTechnologyDispatcher,
            DetectorTechnology,
        )
        decision = EliteTechnologyDispatcher.select_technology(
            ceiling_height_m=height,
            detector_category="smoke",
        )
        assert decision.technology == DetectorTechnology.POINT_SMOKE
        assert decision.spacing_m == pytest.approx(9.1, abs=0.01), (
            f"At h={height}m, smoke spacing = {decision.spacing_m}m, expected 9.1m"
        )

    def test_smoke_reason_mentions_flat_spacing(self):
        """Decision reason must mention flat spacing per §17.7.3.2.3."""
        from fireai.core.nfpa72_technology_dispatcher import (
            EliteTechnologyDispatcher,
        )
        decision = EliteTechnologyDispatcher.select_technology(
            ceiling_height_m=5.0,
            detector_category="smoke",
        )
        assert "17.7.3.2.3" in decision.reason or "flat" in decision.reason.lower(), (
            f"Decision reason should mention flat spacing or §17.7.3.2.3: {decision.reason}"
        )

    def test_smoke_nfpa_refs_include_17_7_3_2_3(self):
        """NFPA references must include §17.7.3.2.3."""
        from fireai.core.nfpa72_technology_dispatcher import (
            EliteTechnologyDispatcher,
        )
        decision = EliteTechnologyDispatcher.select_technology(
            ceiling_height_m=5.0,
            detector_category="smoke",
        )
        has_section = any("17.7.3.2.3" in ref for ref in decision.nfpa_references)
        assert has_section, (
            f"NFPA references should include §17.7.3.2.3: {decision.nfpa_references}"
        )

    def test_high_ceiling_stratification_advisory(self):
        """Heights above 9.1m should get stratification advisory, not reduced spacing."""
        from fireai.core.nfpa72_technology_dispatcher import (
            EliteTechnologyDispatcher,
            DetectorTechnology,
        )
        decision = EliteTechnologyDispatcher.select_technology(
            ceiling_height_m=10.5,
            detector_category="smoke",
        )
        assert decision.technology == DetectorTechnology.POINT_SMOKE
        assert decision.spacing_m == pytest.approx(9.1, abs=0.01)
        # Should have stratification advisory
        has_stratification = any(
            "stratification" in w.lower() or "17.7.1.11" in w
            for w in decision.warnings
        )
        assert has_stratification, (
            f"Expected stratification advisory for h=10.5m, got: {decision.warnings}"
        )


# ============================================================================
# Test 5: SSoT consistency — all modules agree on smoke spacing
# ============================================================================

class TestSSoTConsistency:
    """Verify all modules agree on smoke detector spacing values."""

    def test_all_modules_agree_on_smoke_max_spacing(self):
        """All modules must agree on SMOKE_MAX_SPACING_M = 9.1."""
        from fireai.constants.nfpa72 import SMOKE_MAX_SPACING_M as canonical
        from fireai.constants import SMOKE_MAX_SPACING_M as reexported
        assert canonical == reexported == 9.1

    def test_all_modules_agree_on_smoke_coverage_radius(self):
        """All modules must agree on SMOKE_COVERAGE_RADIUS_M = 6.37."""
        from fireai.constants.nfpa72 import SMOKE_COVERAGE_RADIUS_M as canonical
        from fireai.constants import SMOKE_COVERAGE_RADIUS_M as reexported
        assert canonical == reexported == 6.37

    def test_qomn_kernel_imports_from_canonical(self):
        """qomn_kernel must use the canonical SMOKE_MAX_SPACING_M."""
        from fireai.core.qomn_kernel import NFPA72_SMOKE_MAX_SPACING_M
        from fireai.constants.nfpa72 import SMOKE_MAX_SPACING_M
        assert NFPA72_SMOKE_MAX_SPACING_M == SMOKE_MAX_SPACING_M == 9.1


# ============================================================================
# Test 6: Heat detector spacing is STILL correctly reduced
# ============================================================================

class TestHeatSpacingStillReduced:
    """Verify heat detector height reduction was NOT affected by smoke fix."""

    @pytest.mark.parametrize("height,expected_spacing", [
        (3.0, 6.10),   # No reduction at h<=3.0m
        (4.6, 5.50),   # Reduced
        (6.1, 4.90),   # More reduced
        (9.1, 4.30),   # Further reduced
        (12.2, 3.70),  # Most reduced in table
    ])
    def test_heat_spacing_decreases_correctly(self, height, expected_spacing):
        """Heat detector spacing must match Table 17.6.3.5.1 reduction."""
        from fireai.core.nfpa72_calculations import calculate_coverage_radius_from_height
        spec = calculate_coverage_radius_from_height(height, "heat")
        assert spec.spacing_max == pytest.approx(expected_spacing, abs=0.01), (
            f"Heat spacing at h={height}m = {spec.spacing_max}m, "
            f"expected {expected_spacing}m per Table 17.6.3.5.1"
        )

    def test_heat_height_table_unchanged(self):
        """HEAT_HEIGHT_SPACING_TABLE must have correct reduction values."""
        from fireai.constants.nfpa72 import HEAT_HEIGHT_SPACING_TABLE
        # First entry: h<=3.0m → 6.10m (no reduction)
        assert HEAT_HEIGHT_SPACING_TABLE[0] == (3.0, 6.10)
        # Last entry: h<=12.2m → 3.70m
        assert HEAT_HEIGHT_SPACING_TABLE[-1] == (12.2, 3.70)
        # Verify all values are decreasing
        spacings = [s for _, s in HEAT_HEIGHT_SPACING_TABLE]
        for i in range(1, len(spacings)):
            assert spacings[i] < spacings[i-1], (
                f"Heat spacing not decreasing: {spacings[i]} >= {spacings[i-1]}"
            )
