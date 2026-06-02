"""
qomn_conduit.tests.test_catalog — Catalog Data Validation
==========================================================

Tests all catalog entries have positive dimensions, correct catalog
number patterns, and match NEC published data (golden tests).

Reference: NEC 2022 Chapter 9, Table 4; NEC 358.24, 352.24, 344.24.
"""

import math
import pytest

from qomn_conduit import (
    ConduitType, TradeSize, FittingType,
    get_fitting, catalog_size, all_fittings, Fitting,
)
from qomn_conduit.errors import CatalogError


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: All catalog entries have positive dimensions
# ─────────────────────────────────────────────────────────────────────────────

class TestCatalogPositiveDimensions:
    """Every fitting must have positive OD, weight, and appropriate radius/length."""

    def test_all_fittings_have_positive_od(self):
        """All fittings must have OD > 0."""
        for key, fitting in all_fittings().items():
            assert fitting.od_in > 0.0, (
                f"Fitting {fitting.catalog_number} has OD={fitting.od_in} ≤ 0"
            )

    def test_all_fittings_have_non_negative_weight(self):
        """All fittings must have weight >= 0."""
        for key, fitting in all_fittings().items():
            assert fitting.weight_kg >= 0.0, (
                f"Fitting {fitting.catalog_number} has weight={fitting.weight_kg} < 0"
            )

    def test_elbows_have_positive_bend_radius(self):
        """All elbow fittings must have bend_radius > 0."""
        for key, fitting in all_fittings().items():
            if fitting.fitting_type in (FittingType.ELBOW_90, FittingType.ELBOW_45):
                assert fitting.bend_radius_in > 0.0, (
                    f"Elbow {fitting.catalog_number} has bend_radius={fitting.bend_radius_in} ≤ 0"
                )

    def test_elbows_have_positive_developed_length(self):
        """All elbow fittings must have developed_length > 0."""
        for key, fitting in all_fittings().items():
            if fitting.fitting_type in (FittingType.ELBOW_90, FittingType.ELBOW_45):
                assert fitting.developed_length_in > 0.0, (
                    f"Elbow {fitting.catalog_number} has developed_length={fitting.developed_length_in} ≤ 0"
                )

    def test_couplings_have_positive_body_length(self):
        """All coupling fittings must have body_length > 0."""
        for key, fitting in all_fittings().items():
            if fitting.fitting_type == FittingType.COUPLING:
                assert fitting.body_length_in > 0.0, (
                    f"Coupling {fitting.catalog_number} has body_length={fitting.body_length_in} ≤ 0"
                )


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Catalog lookup returns correct fitting for valid input
# ─────────────────────────────────────────────────────────────────────────────

class TestCatalogLookup:
    """Valid (conduit_type, trade_size, fitting_type) must return the correct fitting."""

    def test_emt_half_inch_elbow_90(self):
        """EMT ½\" ELBOW_90 must return E90-050."""
        result = get_fitting(ConduitType.EMT, TradeSize.HALF_INCH, FittingType.ELBOW_90)
        assert result.is_ok()
        assert result.value.catalog_number == "E90-050"
        assert result.value.od_in == pytest.approx(0.706, abs=0.001)
        assert result.value.bend_radius_in == pytest.approx(4.0, abs=0.001)

    def test_upvc_sch40_three_quarter_elbow_90(self):
        """UPVC Sch40 ¾\" ELBOW_90 must return P90-075."""
        result = get_fitting(ConduitType.UPVC_SCH40, TradeSize.THREE_QUARTER, FittingType.ELBOW_90)
        assert result.is_ok()
        assert result.value.catalog_number == "P90-075"

    def test_rgd_one_inch_elbow_90(self):
        """RGD 1\" ELBOW_90 must return R90-100."""
        result = get_fitting(ConduitType.RGD, TradeSize.ONE_INCH, FittingType.ELBOW_90)
        assert result.is_ok()
        assert result.value.catalog_number == "R90-100"

    def test_upvc_sch80_half_inch_elbow_90(self):
        """UPVC Sch80 ½\" ELBOW_90 must return S90-050."""
        result = get_fitting(ConduitType.UPVC_SCH80, TradeSize.HALF_INCH, FittingType.ELBOW_90)
        assert result.is_ok()
        assert result.value.catalog_number == "S90-050"

    def test_emt_coupling_half_inch(self):
        """EMT ½\" COUPLING must return EC-050."""
        result = get_fitting(ConduitType.EMT, TradeSize.HALF_INCH, FittingType.COUPLING)
        assert result.is_ok()
        assert result.value.catalog_number == "EC-050"
        assert result.value.body_length_in == pytest.approx(1.5, abs=0.001)


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Catalog lookup returns error for invalid combination
# ─────────────────────────────────────────────────────────────────────────────

class TestCatalogInvalidLookup:
    """Invalid combinations must return Result.err(CatalogError)."""

    def test_tee_fitting_not_in_catalog(self):
        """TEE fitting type is not in catalog — must return error."""
        result = get_fitting(ConduitType.EMT, TradeSize.HALF_INCH, FittingType.TEE)
        assert result.is_err()
        assert isinstance(result.error, CatalogError)

    def test_pull_box_not_in_catalog(self):
        """PULL_BOX is not a catalog fitting — must return error."""
        result = get_fitting(ConduitType.EMT, TradeSize.HALF_INCH, FittingType.PULL_BOX)
        assert result.is_err()


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Catalog numbers match expected pattern
# ─────────────────────────────────────────────────────────────────────────────

class TestCatalogNumberPattern:
    """All catalog numbers must follow the [E|P|S|R][90|45|C|S]-[size] pattern."""

    def test_elbow_catalog_numbers_start_with_letter(self):
        """Elbow catalog numbers must start with E, P, S, or R."""
        for key, fitting in all_fittings().items():
            if fitting.fitting_type in (FittingType.ELBOW_90, FittingType.ELBOW_45):
                assert fitting.catalog_number[0] in "EPSR", (
                    f"Elbow {fitting.catalog_number} doesn't start with E/P/S/R"
                )

    def test_coupling_catalog_numbers(self):
        """Coupling catalog numbers must follow EC-/ES-/PC-/RC- pattern."""
        for key, fitting in all_fittings().items():
            if fitting.fitting_type == FittingType.COUPLING:
                assert fitting.catalog_number[:2] in ("EC", "ES", "PC", "RC"), (
                    f"Coupling {fitting.catalog_number} has unexpected prefix"
                )


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: Golden test — E90-050 dimensions match NEC Table
# ─────────────────────────────────────────────────────────────────────────────

class TestGoldenCatalogData:
    """Verified against NEC published dimensional data."""

    def test_e90_050_dimensions(self):
        """E90-050: EMT ½\" elbow — OD=0.706\", R=4.0\", L=6.283\"."""
        result = get_fitting(ConduitType.EMT, TradeSize.HALF_INCH, FittingType.ELBOW_90)
        assert result.is_ok()
        f = result.value
        assert f.catalog_number == "E90-050"
        assert f.od_in == pytest.approx(0.706, abs=0.001)
        assert f.bend_radius_in == pytest.approx(4.0, abs=0.001)
        # Developed length = π × 4.0 / 2 = 6.283
        assert f.developed_length_in == pytest.approx(math.pi * 4.0 / 2, abs=0.001)

    def test_e90_200_dimensions(self):
        """E90-200: EMT 2\" elbow — OD=2.197\", R=9.5\", L=14.922\"."""
        result = get_fitting(ConduitType.EMT, TradeSize.TWO_INCH, FittingType.ELBOW_90)
        assert result.is_ok()
        f = result.value
        assert f.catalog_number == "E90-200"
        assert f.od_in == pytest.approx(2.197, abs=0.001)
        assert f.bend_radius_in == pytest.approx(9.5, abs=0.001)
        assert f.developed_length_in == pytest.approx(math.pi * 9.5 / 2, abs=0.01)

    def test_catalog_size(self):
        """Catalog must have exactly 32 entries."""
        # 6 EMT elbows + 6 UPVC40 elbows + 6 UPVC80 elbows + 6 RGD elbows
        # + 2 EMT-C couplings + 2 EMT-S couplings + 2 UPVC couplings + 2 RGD couplings
        assert catalog_size() == 32


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: Catalog covers all conduit types and trade sizes for elbows
# ─────────────────────────────────────────────────────────────────────────────

class TestCatalogCoverage:
    """All conduit types must have elbow entries for all trade sizes."""

    @pytest.mark.parametrize("ct", [
        ConduitType.EMT, ConduitType.UPVC_SCH40,
        ConduitType.UPVC_SCH80, ConduitType.RGD,
    ])
    @pytest.mark.parametrize("ts", [
        TradeSize.HALF_INCH, TradeSize.THREE_QUARTER,
        TradeSize.ONE_INCH, TradeSize.ONE_QUARTER,
        TradeSize.ONE_HALF, TradeSize.TWO_INCH,
    ])
    def test_elbow_90_exists_for_all_combinations(self, ct, ts):
        """Every (conduit_type, trade_size) combination must have an ELBOW_90."""
        result = get_fitting(ct, ts, FittingType.ELBOW_90)
        assert result.is_ok(), (
            f"Missing ELBOW_90 for {ct.value} {ts.value}"
        )
