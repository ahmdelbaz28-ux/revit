"""
tests/test_v24_spectral_registry.py
====================================
Tests for the 27 new SpectralSignature entries (GAP-3, FireAI V24).
All 27 substances must be retrievable by CAS and have physically
reasonable alpha values (>= 0, not all zero).

Run: pytest tests/test_v24_spectral_registry.py -v
"""

import pytest

from fireai.core.models_v21 import (
    SpectralSignatureRegistry,
    SpectralSignature,
    WavelengthBand,
    VolumetricMedium,
    beer_lambert_transmittance,
)


# All 27 new entries: (CAS, name, must_have_strong_band)
NEW_SUBSTANCES = [
    ("115-07-1",   "Propylene",                  "IR1"),
    ("106-98-9",   "1-Butene",                   "IR1"),
    ("109-66-0",   "n-Pentane",                  "IR1"),
    ("142-82-5",   "n-Heptane",                  "IR1"),
    ("111-65-9",   "n-Octane",                   "IR1"),
    ("111-84-2",   "n-Nonane",                   "IR1"),
    ("124-18-5",   "n-Decane",                   "IR1"),
    ("110-82-7",   "Cyclohexane",                "IR1"),
    ("64742-89-8", "Naphtha (light)",            "IR1"),
    ("8008-20-6",  "Kerosene/Jet-A",             "IR1"),
    ("68334-30-5", "Diesel Fuel",                "IR1"),
    ("8002-05-9",  "Crude Oil Vapor",            "IR1"),
    ("50-00-0",    "Formaldehyde",               "UV"),
    ("78-93-3",    "Methyl Ethyl Ketone",        "UV"),
    ("100-42-5",   "Styrene",                    "UV"),
    ("75-01-4",    "Vinyl Chloride",             "UV"),
    ("75-21-8",    "Ethylene Oxide",             "UV"),
    ("75-56-9",    "Propylene Oxide",            "UV"),
    ("7782-50-5",  "Chlorine",                   "UV"),
    ("7446-09-5",  "Sulfur Dioxide",             "UV"),
    ("10102-43-9", "Nitric Oxide",               "UV"),
    ("7803-51-2",  "Phosphine",                  "IR3"),
    ("7803-62-5",  "Silane",                     "IR3"),
    ("8006-14-2",  "Natural Gas (blend)",        "IR1"),
    ("68476-85-7", "LPG (Propane/Butane blend)", "IR1"),
    ("74-82-8-LNG","LNG Vapor (methane-rich)",   "IR1"),
    ("68919-39-1", "Refinery Gas",               "IR1"),
]

BAND_MAP = {
    "UV":  WavelengthBand.UV,
    "VIS": WavelengthBand.VIS,
    "IR1": WavelengthBand.IR1,
    "IR3": WavelengthBand.IR3,
}

BAND_ALPHA_ATTR = {
    "UV":  "alpha_uv",
    "VIS": "alpha_vis",
    "IR1": "alpha_ir1",
    "IR3": "alpha_ir3",
}


@pytest.fixture(scope="module")
def registry() -> SpectralSignatureRegistry:
    return SpectralSignatureRegistry()


class TestNewSubstancesRegistered:
    """Verify all 27 new substances are in the registry with correct data."""

    @pytest.mark.parametrize("cas,name,strong_band", NEW_SUBSTANCES)
    def test_cas_lookup_returns_correct_name(self, registry, cas, name, strong_band):
        """Every new substance must be retrievable by CAS number."""
        sig = registry.get(cas)
        assert sig is not None, (
            f"CAS {cas} ({name}) not found in SpectralSignatureRegistry. "
            "Ensure it was added to _ensure_loaded()."
        )
        assert sig.substance_name == name, (
            f"Name mismatch for CAS {cas}: "
            f"expected '{name}', got '{sig.substance_name}'"
        )

    @pytest.mark.parametrize("cas,name,strong_band", NEW_SUBSTANCES)
    def test_strong_band_alpha_positive(self, registry, cas, name, strong_band):
        """The declared 'strong' absorption band must have alpha > 0."""
        sig = registry.get(cas)
        attr = BAND_ALPHA_ATTR[strong_band]
        alpha_val = getattr(sig, attr, 0.0)
        assert alpha_val > 0.0, (
            f"{name} (CAS {cas}): {attr} must be > 0 "
            f"(got {alpha_val}). Physical constraint: declared strong band "
            "must have measurable absorption."
        )

    @pytest.mark.parametrize("cas,name,strong_band", NEW_SUBSTANCES)
    def test_all_alpha_nonnegative(self, registry, cas, name, strong_band):
        """All four band alpha values must be >= 0 (physical constraint)."""
        sig = registry.get(cas)
        for band_name in ("alpha_uv", "alpha_vis", "alpha_ir1", "alpha_ir3"):
            val = getattr(sig, band_name, -1.0)
            assert val >= 0.0, (
                f"{name} (CAS {cas}): {band_name}={val} is negative. "
                "Absorption coefficients must be >= 0."
            )

    def test_total_registry_size_at_least_50(self, registry):
        """After adding 27 new substances, total registry must be >= 50."""
        count = registry.count()
        assert count >= 50, (
            f"Registry has {count} substances; expected >= 50 after GAP-3 additions."
        )

    def test_alpha_for_method_works_for_new_substances(self, registry):
        """SpectralSignature.alpha_for() must return correct values."""
        sig = registry.get("115-07-1")  # Propylene
        assert sig is not None
        assert sig.alpha_for(WavelengthBand.IR1) == 2.4
        assert sig.alpha_for(WavelengthBand.UV) == 2.8
        assert sig.alpha_for(WavelengthBand.VIS) == 0.0
        assert sig.alpha_for(WavelengthBand.IR3) == 0.9


class TestBeerLambertWithNewSubstances:
    """Verify Beer-Lambert calculations with new spectral data."""

    def test_propylene_ir1_attenuates_10m_path(self, registry):
        """
        Propylene IR1: alpha=2.4 m^-1 at 1% v/v.
        Over 10 m path: T = exp(-2.4*10) ~ 3.4e-11 -> near zero.
        At 0.1% v/v (cloud edge): alpha_eff = 0.24 m^-1,
        T_10m = exp(-0.24*10) = exp(-2.4) ~ 0.091.
        """
        alpha_1pct = 2.4   # m^-1 at 1% v/v
        alpha_edge = alpha_1pct * 0.1   # 0.1% v/v cloud edge
        T = beer_lambert_transmittance(alpha_edge, 10.0)
        assert 0.05 < T < 0.15, (
            f"Propylene 0.1% v/v, 10m path: expected T~0.091, got {T:.4f}"
        )

    def test_styrene_strong_uv_attenuation(self, registry):
        """
        Styrene UV: alpha=9.0 m^-1 (strong aromatic absorber).
        Even 1 m path at 0.1%: T = exp(-9.0*0.1*1) = exp(-0.9) ~ 0.407.
        """
        T = beer_lambert_transmittance(9.0 * 0.1, 1.0)
        assert 0.35 < T < 0.45

    def test_volumetric_medium_propylene_nonzero(self, registry):
        """
        VolumetricMedium with propylene CAS must return non-zero IR1 alpha.
        """
        medium = VolumetricMedium(
            medium_id="propylene_cloud",
            medium_type="GAS_CLOUD",
            bbox_min=[0.0, 0.0, 0.0],
            bbox_max=[10.0, 10.0, 3.0],
            cas_number="115-07-1",
            concentration_factor=1.0,
        )
        alpha_ir1 = medium.get_alpha_with_registry(
            WavelengthBand.IR1, registry
        )
        assert alpha_ir1 > 0.0, (
            "Propylene GAS_CLOUD: IR1 alpha must be > 0 via registry lookup."
        )

    def test_syngas_co_ir3_contribution(self, registry):
        """
        Syngas (CO+H2 blend): IR3 must be > 0 due to CO S-branch at 4.67 um.
        """
        sig = registry.get("SYNGAS-5050")
        assert sig is not None
        assert sig.alpha_ir3 > 0.0, (
            "Syngas IR3 must be > 0 - CO contributes near-IR3 absorption."
        )

    def test_chlorine_vis_detectable(self, registry):
        """
        Chlorine Cl2 is yellow-green and detectable in VIS band.
        alpha_vis must be > 0.
        """
        sig = registry.get("7782-50-5")
        assert sig.alpha_vis > 0.0, (
            "Chlorine must have alpha_vis > 0 - visible yellow-green color."
        )

    def test_lng_vapor_dominates_ir1(self, registry):
        """
        LNG vapor (methane-rich): IR1 must be the dominant band.
        """
        sig = registry.get("74-82-8-LNG")
        assert sig.alpha_ir1 > sig.alpha_uv,  "LNG: IR1 > UV"
        assert sig.alpha_ir1 > sig.alpha_vis, "LNG: IR1 > VIS"
        assert sig.alpha_ir1 > sig.alpha_ir3, "LNG: IR1 > IR3 (CH4 fingerprint)"

    def test_diesel_uv_higher_than_pentane(self, registry):
        """
        Diesel has aromatic content -> higher UV than pure alkane (pentane).
        """
        sig_diesel  = registry.get("68334-30-5")
        sig_pentane = registry.get("109-66-0")
        assert sig_diesel.alpha_uv > sig_pentane.alpha_uv, (
            "Diesel UV alpha must exceed n-pentane UV (aromatics present in diesel)."
        )

    def test_phosphine_silane_ir3_strong(self, registry):
        """
        PH3 and SiH4: P-H and Si-H stretches produce IR3 absorption.
        Both must have alpha_ir3 > 1.0 m^-1.
        """
        for cas, name in [("7803-51-2", "Phosphine"), ("7803-62-5", "Silane")]:
            sig = registry.get(cas)
            assert sig.alpha_ir3 > 1.0, (
                f"{name} (CAS {cas}): alpha_ir3 must be > 1.0 "
                f"(P-H / Si-H stretch; got {sig.alpha_ir3})"
            )


class TestExistingSubstancesUnchanged:
    """Verify that the 23 original substances still work correctly."""

    def test_methane_still_works(self, registry):
        sig = registry.get("74-82-8")
        assert sig is not None
        assert sig.substance_name == "Methane"
        assert sig.alpha_ir3 == 0.4  # V30 FIX: corrected from 0.8 per HITRAN 2020

    def test_propane_still_works(self, registry):
        sig = registry.get("74-98-6")
        assert sig is not None
        assert sig.substance_name == "Propane"

    def test_hydrogen_still_works(self, registry):
        sig = registry.get("1333-74-0")
        assert sig is not None
        assert sig.substance_name == "Hydrogen"
        # H2 has no IR absorption
        assert sig.alpha_ir1 == 0.0
        assert sig.alpha_ir3 == 0.0

    def test_benzene_still_works(self, registry):
        sig = registry.get("71-43-2")
        assert sig is not None
        assert sig.substance_name == "Benzene"
        assert sig.alpha_uv == 8.5  # Strong aromatic UV


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
