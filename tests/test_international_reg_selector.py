# NOSONAR
"""
tests/test_international_reg_selector.py
============================================
Comprehensive test suite for:
  - fireai/core/international_reg_selector.py

SAFETY CRITICAL: Regulatory jurisdiction selection is a LEGAL GATE.
Wrong jurisdiction = illegal design = potential criminal liability.
Canada must use CEC Zone system (not NEC Division) since 1998.

References:
  NFPA 70 Art. 500-506 — NEC Division system
  CEC Section 18 — Canadian Zone system
  ATEX 2014/34/EU — European Zone system
  IEC 60079 series — International Zone system
  Fix #1: Canada → CEC_ZONE (not NEC_DIVISION)
  Fix #3: Norway → EFTA (not EU)
  Fix #4: CLASS_III has no IEC zone equivalent
  Q3: UnknownCountryError RAISES instead of silent fallback

"""

from __future__ import annotations

import pytest

from fireai.core.international_reg_selector import (
    COUNTRY_FRAMEWORK_MAP,
    DIVISION_TO_ZONE,
    ZONE_TO_DIVISION,
    ATEXZone,
    HazardClass,
    HazardSystem,
    InternationalRegSelector,
    JurisdictionRegion,
    JurisdictionResult,
    NECDivision,
    RegulatoryFrameworkLegacy,
    UnknownCountryError,
    convert_division_to_zone,
    resolve,
)
from fireai.core.models_v21 import RegSelectorResult, RegulatoryFramework

# Enums
# ─────────────────────────────────────────────────────────────────────────────


class TestHazardSystem:
    def test_all_systems(self):
        expected = {
            "NEC_DIVISION", "CEC_ZONE", "ATEX_ZONE",
            "IECEX_ZONE", "AS_NZS_ZONE", "GOST_ZONE", "GB_ZONE",
        }
        actual = {s.value for s in HazardSystem}
        assert actual == expected


class TestJurisdictionRegion:
    def test_key_regions(self):
        key_regions = {"USA", "CANADA", "EU", "EFTA", "UK", "AUSTRALIA", "CHINA"}
        actual = {r.value for r in JurisdictionRegion}
        for r in key_regions:
            assert r in actual


class TestHazardClass:
    def test_all_classes(self):
        expected = {"CLASS_I", "CLASS_II", "CLASS_III", "GAS_VAPOR", "DUST"}
        actual = {c.value for c in HazardClass}
        assert expected == actual


class TestNECDivision:
    def test_divisions(self):
        assert {d.value for d in NECDivision} == {"DIVISION_1", "DIVISION_2"}


class TestATEXZone:
    def test_zones(self):
        expected = {
            "ZONE_0", "ZONE_1", "ZONE_2",
            "ZONE_20", "ZONE_21", "ZONE_22", "SAFE",
        }
        actual = {z.value for z in ATEXZone}
        assert expected == actual


# ─────────────────────────────────────────────────────────────────────────────
# UnknownCountryError — Q3 FIX
# ─────────────────────────────────────────────────────────────────────────────


class TestUnknownCountryError:
    def test_raises_for_unknown_country(self):
        with pytest.raises(UnknownCountryError) as exc_info:
            resolve("XX")
        assert "XX" in str(exc_info.value)
        assert exc_info.value.country_code == "XX"

    def test_error_message_contains_legal_warning(self):
        try:
            resolve("UNKNOWN_COUNTRY")
        except UnknownCountryError as e:
            assert "criminal liability" in str(e).lower() or "legal" in str(e).lower()

    def test_is_exception(self):
        assert issubclass(UnknownCountryError, Exception)


# COUNTRY_FRAMEWORK_MAP
# ─────────────────────────────────────────────────────────────────────────────


class TestCountryFrameworkMap:
    """Fix #1: Canada → CEC, Fix #3: Norway → EFTA, Fix #5: +15 countries."""

    def test_usa_nec(self):
        assert COUNTRY_FRAMEWORK_MAP["US"] == RegulatoryFramework.NEC_US
        assert COUNTRY_FRAMEWORK_MAP["USA"] == RegulatoryFramework.NEC_US

    def test_canada_cec_fix1(self):
        """Fix #1: Canada uses CEC Zone system since 1998."""
        assert COUNTRY_FRAMEWORK_MAP["CA"] == RegulatoryFramework.CEC_CANADA
        assert COUNTRY_FRAMEWORK_MAP["CANADA"] == RegulatoryFramework.CEC_CANADA

    def test_germany_atex(self):
        assert COUNTRY_FRAMEWORK_MAP["DE"] == RegulatoryFramework.ATEX_EU
        assert COUNTRY_FRAMEWORK_MAP["GERMANY"] == RegulatoryFramework.ATEX_EU

    def test_norway_efta_fix3(self):
        """Fix #3: Norway → EFTA (not EU member)."""
        assert COUNTRY_FRAMEWORK_MAP["NO"] == RegulatoryFramework.EFTA
        assert COUNTRY_FRAMEWORK_MAP["NORWAY"] == RegulatoryFramework.EFTA

    def test_switzerland_efta(self):
        assert COUNTRY_FRAMEWORK_MAP["CH"] == RegulatoryFramework.EFTA
        assert COUNTRY_FRAMEWORK_MAP["SWITZERLAND"] == RegulatoryFramework.EFTA

    def test_iceland_efta(self):
        assert COUNTRY_FRAMEWORK_MAP["IS"] == RegulatoryFramework.EFTA

    def test_australia_iecex(self):
        assert COUNTRY_FRAMEWORK_MAP["AU"] == RegulatoryFramework.IECEX
        assert COUNTRY_FRAMEWORK_MAP["AUSTRALIA"] == RegulatoryFramework.IECEX

    def test_mexico_nec(self):
        assert COUNTRY_FRAMEWORK_MAP["MX"] == RegulatoryFramework.NEC_US

    def test_case_insensitive_country_codes(self):
        """Full country names must also be mapped."""
        assert COUNTRY_FRAMEWORK_MAP["FRANCE"] == RegulatoryFramework.ATEX_EU
        assert COUNTRY_FRAMEWORK_MAP["JAPAN"] == RegulatoryFramework.IECEX
        assert COUNTRY_FRAMEWORK_MAP["BRAZIL"] == RegulatoryFramework.IECEX
        assert COUNTRY_FRAMEWORK_MAP["INDIA"] == RegulatoryFramework.IECEX


# ─────────────────────────────────────────────────────────────────────────────
# resolve() — V21 API
# ─────────────────────────────────────────────────────────────────────────────


class TestResolve:
    def test_usa_returns_nec(self):
        result = resolve("US")
        assert isinstance(result, RegSelectorResult)
        assert result.framework == RegulatoryFramework.NEC_US
        assert result.zone_system == "DIVISION"

    def test_canada_returns_cec(self):
        result = resolve("CA")
        assert result.framework == RegulatoryFramework.CEC_CANADA
        assert result.zone_system == "ZONE"

    def test_germany_returns_atex(self):
        result = resolve("DE")
        assert result.framework == RegulatoryFramework.ATEX_EU
        assert result.zone_system == "ZONE"

    def test_norway_returns_efta_with_warning(self):
        result = resolve("NO")
        assert result.framework == RegulatoryFramework.EFTA
        assert len(result.warnings) >= 1
        assert any("EFTA" in w or "DSB" in w for w in result.warnings)

    def test_unknown_raises_unknown_country_error(self):
        with pytest.raises(UnknownCountryError):
            resolve("XX")

    def test_case_insensitive(self):
        r1 = resolve("us")
        r2 = resolve("US")
        assert r1.framework == r2.framework

    def test_whitespace_stripped(self):
        r1 = resolve("  US  ")
        r2 = resolve("US")
        assert r1.framework == r2.framework


# convert_division_to_zone
# ─────────────────────────────────────────────────────────────────────────────


class TestConvertDivisionToZone:
    """Fix #2: Division-to-Zone conversion with hazard class distinction."""

    def test_div1_class1_zone1(self):
        assert convert_division_to_zone("DIVISION_1", "CLASS_I") == "ZONE_1"

    def test_div2_class1_zone2(self):
        assert convert_division_to_zone("DIVISION_2", "CLASS_I") == "ZONE_2"

    def test_div1_class2_zone21(self):
        """Dust zones are different from gas zones."""
        assert convert_division_to_zone("DIVISION_1", "CLASS_II") == "ZONE_21"

    def test_div2_class2_zone22(self):
        assert convert_division_to_zone("DIVISION_2", "CLASS_II") == "ZONE_22"

    def test_class3_no_equivalent_fix4(self):
        """Fix #4: CLASS_III has NO IEC Zone equivalent."""
        with pytest.raises(ValueError, match="CLASS_III"):
            convert_division_to_zone("DIVISION_1", "CLASS_III")

    def test_class3_div2_no_equivalent(self):
        with pytest.raises(ValueError, match="CLASS_III"):
            convert_division_to_zone("DIVISION_2", "CLASS_III")

    def test_unknown_combination_raises(self):
        with pytest.raises(ValueError, match="Unknown"):
            convert_division_to_zone("DIVISION_99", "CLASS_I")

    def test_case_insensitive(self):
        assert convert_division_to_zone("division_1", "class_i") == "ZONE_1"


# ─────────────────────────────────────────────────────────────────────────────
# InternationalRegSelector (legacy class)
# ─────────────────────────────────────────────────────────────────────────────


class TestInternationalRegSelector:
    @pytest.fixture
    def selector(self):
        return InternationalRegSelector()

    def test_resolve_usa(self, selector):
        result = selector.resolve("US")
        assert isinstance(result, JurisdictionResult)
        assert result.is_valid
        assert result.region == JurisdictionRegion.USA
        assert result.system == HazardSystem.NEC_DIVISION

    def test_resolve_canada_cec_fix1(self, selector):
        """Fix #1: Canada → CEC Zone system."""
        result = selector.resolve("CA")
        assert result.region == JurisdictionRegion.CANADA
        assert result.system == HazardSystem.CEC_ZONE

    def test_resolve_germany_atex(self, selector):
        result = selector.resolve("DE")
        assert result.region == JurisdictionRegion.EU
        assert result.system == HazardSystem.ATEX_ZONE

    def test_resolve_norway_efta_fix3(self, selector):
        result = selector.resolve("NO")
        assert result.region == JurisdictionRegion.EFTA
        assert len(result.warnings) >= 1

    def test_resolve_unknown_defaults_to_global(self, selector):
        """Unknown country defaults to GLOBAL/IECEx with warning."""
        result = selector.resolve("XX")
        assert result.region == JurisdictionRegion.GLOBAL
        assert any("not in jurisdiction" in w.lower() for w in result.warnings)

    def test_resolve_v21_matches_resolve(self, selector):
        """V21 interface should produce consistent results."""
        r_v21 = selector.resolve_v21("US")
        r_legacy = selector.resolve("US")
        assert r_v21.framework == RegulatoryFramework.NEC_US
        assert r_legacy.system == HazardSystem.NEC_DIVISION

    def test_canada_nec_override_warning(self, selector):
        """Canada + NEC override must generate LEGAL WARNING."""
        result = selector.resolve("CA", override_system=HazardSystem.NEC_DIVISION)
        assert any("LEGAL WARNING" in w for w in result.warnings)

    def test_override_system_changes_result(self, selector):
        result = selector.resolve("DE", override_system=HazardSystem.IECEX_ZONE)
        assert result.system == HazardSystem.IECEX_ZONE

    def test_convert_zone_to_division(self, selector):
        div = selector.convert_zone_to_division(ATEXZone.ZONE_1, HazardClass.CLASS_I)
        assert div == NECDivision.DIVISION_1

    def test_convert_zone2_to_div2(self, selector):
        div = selector.convert_zone_to_division(ATEXZone.ZONE_2, HazardClass.CLASS_I)
        assert div == NECDivision.DIVISION_2

    def test_convert_safe_zone_returns_none(self, selector):
        div = selector.convert_zone_to_division(ATEXZone.SAFE)
        assert div is None

    def test_convert_div1_to_zone1(self, selector):
        zone = selector.convert_division_to_zone(
            NECDivision.DIVISION_1, HazardClass.CLASS_I
        )
        assert zone == ATEXZone.ZONE_1

    def test_convert_div2_to_zone2(self, selector):
        zone = selector.convert_division_to_zone(
            NECDivision.DIVISION_2, HazardClass.CLASS_I
        )
        assert zone == ATEXZone.ZONE_2

    def test_class3_div1_returns_none(self, selector):
        """Fix #4: CLASS_III has no IEC zone equivalent."""
        zone = selector.convert_division_to_zone(
            NECDivision.DIVISION_1, HazardClass.CLASS_III
        )
        assert zone is None

    def test_list_supported_countries(self, selector):
        countries = selector.list_supported_countries()
        assert "US" in countries
        assert "CA" in countries
        assert "DE" in countries
        assert "NO" in countries

    def test_get_framework(self, selector):
        fw = selector.get_framework(HazardSystem.NEC_DIVISION)
        assert isinstance(fw, RegulatoryFrameworkLegacy)
        assert fw.system == HazardSystem.NEC_DIVISION
        assert "NFPA 70" in fw.primary_standard


# RegulatoryFrameworkLegacy
# ─────────────────────────────────────────────────────────────────────────────


class TestRegulatoryFrameworkLegacy:
    def test_frozen(self):
        fw = RegulatoryFrameworkLegacy(
            region=JurisdictionRegion.USA,
            system=HazardSystem.NEC_DIVISION,
            primary_standard="NFPA 70",
        )
        with pytest.raises(AttributeError):
            fw.region = JurisdictionRegion.EU  # frozen

    def test_defaults(self):
        fw = RegulatoryFrameworkLegacy(
            region=JurisdictionRegion.USA,
            system=HazardSystem.NEC_DIVISION,
            primary_standard="NFPA 70",
        )
        assert fw.zone_based is True
        assert fw.requires_notified_body is False
        assert fw.secondary_standards == ()


# JurisdictionResult
# ─────────────────────────────────────────────────────────────────────────────


class TestJurisdictionResult:
    def test_is_valid_no_errors(self):
        r = JurisdictionResult(
            country_input="US",
            region=JurisdictionRegion.USA,
            framework=RegulatoryFrameworkLegacy(
                region=JurisdictionRegion.USA,
                system=HazardSystem.NEC_DIVISION,
                primary_standard="NFPA 70",
            ),
        )
        assert r.is_valid is True

    def test_is_valid_with_errors(self):
        r = JurisdictionResult(
            country_input="XX",
            region=JurisdictionRegion.GLOBAL,
            framework=RegulatoryFrameworkLegacy(
                region=JurisdictionRegion.GLOBAL,
                system=HazardSystem.IECEX_ZONE,
                primary_standard="IEC 60079",
            ),
            errors=("Unknown country",),
        )
        assert r.is_valid is False

    def test_system_property(self):
        fw = RegulatoryFrameworkLegacy(
            region=JurisdictionRegion.USA,
            system=HazardSystem.NEC_DIVISION,
            primary_standard="NFPA 70",
        )
        r = JurisdictionResult(
            country_input="US",
            region=JurisdictionRegion.USA,
            framework=fw,
        )
        assert r.system == HazardSystem.NEC_DIVISION


# ─────────────────────────────────────────────────────────────────────────────
# Division-Zone Mapping Tables
# ─────────────────────────────────────────────────────────────────────────────


class TestDivisionZoneMaps:
    def test_division_to_zone_gas_class1(self):
        assert DIVISION_TO_ZONE[(NECDivision.DIVISION_1, HazardClass.CLASS_I)] == ATEXZone.ZONE_1
        assert DIVISION_TO_ZONE[(NECDivision.DIVISION_2, HazardClass.CLASS_I)] == ATEXZone.ZONE_2

    def test_division_to_zone_dust_class2(self):
        assert DIVISION_TO_ZONE[(NECDivision.DIVISION_1, HazardClass.CLASS_II)] == ATEXZone.ZONE_21
        assert DIVISION_TO_ZONE[(NECDivision.DIVISION_2, HazardClass.CLASS_II)] == ATEXZone.ZONE_22

    def test_class3_returns_none(self):
        assert DIVISION_TO_ZONE[(NECDivision.DIVISION_1, HazardClass.CLASS_III)] is None

    def test_zone_to_division_roundtrip(self):
        """Zone → Division mapping must be consistent with Division → Zone."""
        for (_div, _cls), zone in DIVISION_TO_ZONE.items():
            if zone is not None:
                reverse = ZONE_TO_DIVISION.get(zone)
                assert reverse is not None, f"No reverse mapping for {zone}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
