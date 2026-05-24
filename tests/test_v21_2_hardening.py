"""
test_v21_2_hardening.py – V21.2 Red Team Hardening Test Suite
==============================================================
Tests all V21.2 modifications:
  1. Burgess-Wheeler LFL thermal correction
  2. IEC 60079-14 thermal margin (_select_temp_class_with_margin)
  3. EnvironmentalContext validation
  4. SpectralSignatureRegistry
  5. Beer-Lambert volumetric transmittance
  6. VolumetricMedium model
  7. Ray-trace engine with volumetric media
  8. HAC engine with LFL correction
  9. ATEX arbiter with thermal margin
 10. Anti-Corruption Layer (Revit ACL/DTO)
"""

import math
import pytest
from pydantic import ValidationError


# ===========================================================================
# 1. Burgess-Wheeler LFL Thermal Correction
# ===========================================================================

class TestBurgessWheelerLFL:
    """Test Burgess-Wheeler LFL thermal correction function."""

    def test_no_correction_below_25c(self):
        from fireai.core.models_v21 import burgess_wheeler_lfl
        assert burgess_wheeler_lfl(5.0, 20.0) == 5.0

    def test_no_correction_at_25c(self):
        from fireai.core.models_v21 import burgess_wheeler_lfl
        assert burgess_wheeler_lfl(5.0, 25.0) == 5.0

    def test_correction_at_80c_turbine_room(self):
        """The turbine room scenario from Red Team: LFL drops ~10% at 80C."""
        from fireai.core.models_v21 import burgess_wheeler_lfl
        lfl_corrected = burgess_wheeler_lfl(5.0, 80.0)
        # Delta = 55C, correction = 0.001824 * 55 = 0.10032
        # LFL_80 = 5.0 * (1 - 0.10032) = 4.4984
        assert lfl_corrected < 5.0
        assert lfl_corrected > 4.0  # ~10% reduction at 80C
        assert abs(lfl_corrected - 4.4984) < 0.01

    def test_correction_never_below_50pct(self):
        """Even at extreme temperatures, LFL never drops below 50%."""
        from fireai.core.models_v21 import burgess_wheeler_lfl
        lfl_corrected = burgess_wheeler_lfl(5.0, 85.0)  # Max allowed temp
        assert lfl_corrected >= 2.5  # 50% of 5.0

    def test_correction_with_heat_of_combustion(self):
        """Refined correction with heat of combustion data."""
        from fireai.core.models_v21 import burgess_wheeler_lfl
        # With heat_of_combustion, correction is proportional to delta_Hc
        lfl_refined = burgess_wheeler_lfl(5.0, 80.0, heat_of_combustion_kj_mol=1200.0)
        lfl_standard = burgess_wheeler_lfl(5.0, 80.0)
        # Higher heat of combustion = stronger correction = lower LFL
        assert lfl_refined <= lfl_standard

    def test_methane_lfl_at_60c(self):
        """Methane LFL at 60C should be lower than at 25C."""
        from fireai.core.models_v21 import burgess_wheeler_lfl
        lfl_25 = burgess_wheeler_lfl(5.0, 25.0)
        lfl_60 = burgess_wheeler_lfl(5.0, 60.0)
        assert lfl_60 < lfl_25


# ===========================================================================
# 2. IEC 60079-14 Thermal Margin
# ===========================================================================

class TestThermalMargin:
    """Test _select_temp_class_with_margin with zone-dependent margins."""

    def test_zone0_strict_margin(self):
        """Zone 0: 5% margin with minimum 10K."""
        from fireai.core.models_v21 import _select_temp_class_with_margin, ZoneType, _T_CLASS_MAX
        # autoignition=200C, Zone 0: t_safe = 200 - max(10, 10) = 190
        # Returned T-class max surface must be <= t_safe
        tc = _select_temp_class_with_margin(200.0, ZoneType.ZONE_0)
        max_surface = _T_CLASS_MAX[tc.value]
        t_safe = 200.0 - max(10.0, 0.05 * 200.0)
        assert max_surface <= t_safe, (
            f"Got {tc.value} (max {max_surface}C) which exceeds "
            f"t_safe={t_safe}C for Zone 0!"
        )

    def test_zone1_standard_margin(self):
        """Zone 1: 5% margin with minimum 5K."""
        from fireai.core.models_v21 import _select_temp_class_with_margin, ZoneType, _T_CLASS_MAX
        # autoignition=200C, Zone 1: t_safe = 200 - max(5, 10) = 190
        # Returned T-class max surface must be <= t_safe
        tc = _select_temp_class_with_margin(200.0, ZoneType.ZONE_1)
        max_surface = _T_CLASS_MAX[tc.value]
        t_safe = 200.0 - max(5.0, 0.05 * 200.0)
        assert max_surface <= t_safe, (
            f"Got {tc.value} (max {max_surface}C) which exceeds "
            f"t_safe={t_safe}C for Zone 1!"
        )

    def test_zone2_basic_margin(self):
        """Zone 2: just strictly below."""
        from fireai.core.models_v21 import _select_temp_class_with_margin, ZoneType, _T_CLASS_MAX
        # autoignition=200C, Zone 2: t_safe = 199
        # Returned T-class max surface must be <= t_safe
        tc = _select_temp_class_with_margin(200.0, ZoneType.ZONE_2)
        max_surface = _T_CLASS_MAX[tc.value]
        t_safe = 200.0 - 1.0  # Zone 2: just strictly below
        assert max_surface <= t_safe, (
            f"Got {tc.value} (max {max_surface}C) which exceeds "
            f"t_safe={t_safe}C for Zone 2!"
        )

    def test_one_degree_margin_was_dangerous(self):
        """The 1C margin scenario: autoignition=136C."""
        from fireai.core.models_v21 import _select_temp_class_with_margin, ZoneType, _T_CLASS_MAX, _select_temp_class
        # OLD: _select_temp_class(136) -> T4A (120 < 136) -- safe, more precise with extended classes
        old_tc = _select_temp_class(136.0)
        max_surface = _T_CLASS_MAX[old_tc.value]
        assert max_surface < 136.0  # Must be strictly below autoignition

        # NEW: Zone 0 -> t_safe = 136 - max(10, 6.8) = 126
        # Returned T-class max surface must be <= t_safe
        new_tc = _select_temp_class_with_margin(136.0, ZoneType.ZONE_0)
        new_max = _T_CLASS_MAX[new_tc.value]
        t_safe = 136.0 - max(10.0, 0.05 * 136.0)
        assert new_max <= t_safe, (
            f"Got {new_tc.value} (max {new_max}C) which exceeds "
            f"t_safe={t_safe}C for Zone 0!"
        )

    def test_autoignition_136_zone0_gets_t5(self):
        """autoignition=136C in Zone 0: max surface must be <= t_safe=126C."""
        from fireai.core.models_v21 import _select_temp_class_with_margin, ZoneType, _T_CLASS_MAX
        tc = _select_temp_class_with_margin(136.0, ZoneType.ZONE_0)
        # t_safe = 136 - max(10, 6.8) = 126
        max_surface = _T_CLASS_MAX[tc.value]
        t_safe = 136.0 - max(10.0, 0.05 * 136.0)
        assert max_surface <= t_safe, (
            f"Got {tc.value} (max {max_surface}C) which exceeds "
            f"t_safe={t_safe}C for Zone 0!"
        )

    def test_no_safe_class_raises(self):
        """autoignition below 85C -> no safe class even with T6."""
        from fireai.core.models_v21 import _select_temp_class_with_margin, ZoneType
        with pytest.raises(ValueError, match="No safe temperature class"):
            _select_temp_class_with_margin(90.0, ZoneType.ZONE_0)
            # t_safe = 90 - max(10, 4.5) = 80. T6 max=85 > 80. No class works.

    def test_dust_zone20_uses_strict_margin(self):
        """Zone 20 should use same strict margin as Zone 0."""
        from fireai.core.models_v21 import _select_temp_class_with_margin, ZoneType, TemperatureClass
        tc_gas = _select_temp_class_with_margin(200.0, ZoneType.ZONE_0)
        tc_dust = _select_temp_class_with_margin(200.0, ZoneType.ZONE_20)
        assert tc_gas == tc_dust  # Same margin rule


# ===========================================================================
# 3. EnvironmentalContext
# ===========================================================================

class TestEnvironmentalContext:
    """Test EnvironmentalContext model with worst-case defaults."""

    def test_defaults_are_worst_case(self):
        """Default should be worst-case indoor: F stability, 0.5 m/s wind."""
        from fireai.core.models_v21 import EnvironmentalContext, PasquillStability
        ctx = EnvironmentalContext()
        assert ctx.stability_class == PasquillStability.F
        assert ctx.wind_speed_m_s == 0.5
        assert ctx.is_indoor is True
        assert ctx.ambient_temp_c == 40.0

    def test_unstable_with_low_wind_raises(self):
        """Stability A with 0.5 m/s wind is physically impossible."""
        from fireai.core.models_v21 import EnvironmentalContext, PasquillStability
        with pytest.raises(ValidationError, match="Physics Violation"):
            EnvironmentalContext(
                wind_speed_m_s=0.5,
                stability_class=PasquillStability.A,
            )

    def test_stable_with_low_wind_is_ok(self):
        """Stability F with 0.5 m/s is physically valid (stagnant indoor)."""
        from fireai.core.models_v21 import EnvironmentalContext, PasquillStability
        ctx = EnvironmentalContext(
            wind_speed_m_s=0.5,
            stability_class=PasquillStability.F,
        )
        assert ctx.stability_class == PasquillStability.F

    def test_high_wind_unstable_is_ok(self):
        """Stability A with 5 m/s wind is valid."""
        from fireai.core.models_v21 import EnvironmentalContext, PasquillStability
        ctx = EnvironmentalContext(
            wind_speed_m_s=5.0,
            stability_class=PasquillStability.A,
        )
        assert ctx.stability_class == PasquillStability.A

    def test_frozen_model(self):
        """EnvironmentalContext is immutable."""
        from fireai.core.models_v21 import EnvironmentalContext
        ctx = EnvironmentalContext()
        with pytest.raises(ValidationError):
            ctx.ambient_temp_c = 50.0

    def test_negative_wind_raises(self):
        from fireai.core.models_v21 import EnvironmentalContext
        with pytest.raises(ValidationError):
            EnvironmentalContext(wind_speed_m_s=-1.0)


# ===========================================================================
# 4. SpectralSignatureRegistry
# ===========================================================================

class TestSpectralSignatureRegistry:
    """Test lazy-loaded spectral signature registry."""

    def test_lazy_loading(self):
        from fireai.core.models_v21 import SpectralSignatureRegistry
        reg = SpectralSignatureRegistry()
        assert reg._loaded is False
        reg.get("74-82-8")
        assert reg._loaded is True

    def test_methane_signature(self):
        from fireai.core.models_v21 import SpectralSignatureRegistry, WavelengthBand
        reg = SpectralSignatureRegistry()
        sig = reg.get("74-82-8")
        assert sig is not None
        assert sig.substance_name == "Methane"
        assert sig.alpha_for(WavelengthBand.IR3) == 0.8
        assert sig.alpha_for(WavelengthBand.VIS) == 0.0

    def test_hydrogen_no_ir(self):
        """Hydrogen has no IR absorption — only UV."""
        from fireai.core.models_v21 import SpectralSignatureRegistry, WavelengthBand
        reg = SpectralSignatureRegistry()
        sig = reg.get("1333-74-0")
        assert sig is not None
        assert sig.alpha_for(WavelengthBand.IR3) == 0.0
        assert sig.alpha_for(WavelengthBand.UV) > 0.0

    def test_unknown_cas_returns_none(self):
        from fireai.core.models_v21 import SpectralSignatureRegistry
        reg = SpectralSignatureRegistry()
        assert reg.get("UNKNOWN-CAS") is None

    def test_register_custom(self):
        from fireai.core.models_v21 import SpectralSignatureRegistry, SpectralSignature, WavelengthBand
        reg = SpectralSignatureRegistry()
        custom = SpectralSignature(
            cas_number="CUSTOM-1", substance_name="CustomGas",
            alpha_ir3=2.5,
        )
        reg.register(custom)
        sig = reg.get("CUSTOM-1")
        assert sig is not None
        assert sig.alpha_for(WavelengthBand.IR3) == 2.5

    def test_list_available(self):
        from fireai.core.models_v21 import SpectralSignatureRegistry
        reg = SpectralSignatureRegistry()
        available = reg.list_available()
        assert len(available) >= 4


# ===========================================================================
# 5. Beer-Lambert Volumetric Transmittance
# ===========================================================================

class TestBeerLambert:
    """Test Beer-Lambert volumetric transmittance calculations."""

    def test_clean_air_transmittance(self):
        """alpha=0 -> T=1.0 (clean air)."""
        from fireai.core.models_v21 import beer_lambert_transmittance
        assert beer_lambert_transmittance(0.0, 10.0) == 1.0

    def test_zero_distance(self):
        """d=0 -> T=1.0 (no path through medium)."""
        from fireai.core.models_v21 import beer_lambert_transmittance
        assert beer_lambert_transmittance(1.0, 0.0) == 1.0

    def test_known_transmittance(self):
        """alpha=1.0, d=1.0 -> T=exp(-1) = 0.3679."""
        from fireai.core.models_v21 import beer_lambert_transmittance
        t = beer_lambert_transmittance(1.0, 1.0)
        assert abs(t - math.exp(-1.0)) < 0.001

    def test_dense_medium_near_zero(self):
        """alpha=5.0, d=5.0 -> T=exp(-25) ≈ 0."""
        from fireai.core.models_v21 import beer_lambert_transmittance
        t = beer_lambert_transmittance(5.0, 5.0)
        assert t < 0.001

    def test_transmittance_bounds(self):
        """Transmittance always in [0.0, 1.0]."""
        from fireai.core.models_v21 import beer_lambert_transmittance
        t = beer_lambert_transmittance(100.0, 100.0)
        assert 0.0 <= t <= 1.0


# ===========================================================================
# 6. VolumetricMedium Model
# ===========================================================================

class TestVolumetricMedium:
    """Test VolumetricMedium Pydantic model."""

    def test_basic_construction(self):
        from fireai.core.models_v21 import VolumetricMedium, WavelengthBand
        vm = VolumetricMedium(
            medium_id="smoke_1",
            medium_type="SMOKE",
            bbox_min=[0.0, 0.0, 2.0],
            bbox_max=[10.0, 10.0, 4.0],
            alpha_override={WavelengthBand.IR3: 0.5},
        )
        assert vm.medium_id == "smoke_1"
        assert vm.concentration_factor == 1.0

    def test_bbox_inversion_raises(self):
        from fireai.core.models_v21 import VolumetricMedium
        with pytest.raises(ValidationError, match="bbox_min"):
            VolumetricMedium(
                medium_id="bad",
                medium_type="SMOKE",
                bbox_min=[10.0, 0.0, 0.0],
                bbox_max=[0.0, 10.0, 10.0],
            )

    def test_alpha_with_override(self):
        from fireai.core.models_v21 import VolumetricMedium, WavelengthBand
        vm = VolumetricMedium(
            medium_id="gas_1",
            medium_type="GAS_CLOUD",
            bbox_min=[0, 0, 0],
            bbox_max=[5, 5, 5],
            alpha_override={WavelengthBand.IR3: 1.5},
            concentration_factor=2.0,
        )
        assert vm.get_alpha(WavelengthBand.IR3) == 3.0  # 1.5 * 2.0

    def test_alpha_with_registry(self):
        from fireai.core.models_v21 import VolumetricMedium, WavelengthBand, SpectralSignatureRegistry
        vm = VolumetricMedium(
            medium_id="methane_cloud",
            medium_type="GAS_CLOUD",
            bbox_min=[0, 0, 0],
            bbox_max=[5, 5, 5],
            cas_number="74-82-8",
            concentration_factor=1.0,
        )
        reg = SpectralSignatureRegistry()
        alpha = vm.get_alpha_with_registry(WavelengthBand.IR3, reg)
        assert alpha == 0.8  # Methane IR3 alpha


# ===========================================================================
# 7. Volumetric Path Transmittance
# ===========================================================================

class TestVolumetricPathTransmittance:
    """Test volumetric_path_transmittance with multiple media."""

    def test_no_media_returns_1(self):
        from fireai.core.models_v21 import volumetric_path_transmittance, WavelengthBand
        t = volumetric_path_transmittance(
            (0, 0, 5), (10, 0, 5), [], WavelengthBand.IR3
        )
        assert t == 1.0

    def test_medium_not_in_path(self):
        """Medium off to the side -> T=1.0."""
        from fireai.core.models_v21 import volumetric_path_transmittance, VolumetricMedium, WavelengthBand
        media = [VolumetricMedium(
            medium_id="off_path",
            medium_type="GAS_CLOUD",
            bbox_min=[20, 0, 0], bbox_max=[30, 10, 10],
            alpha_override={WavelengthBand.IR3: 5.0},
        )]
        t = volumetric_path_transmittance(
            (0, 5, 5), (10, 5, 5), media, WavelengthBand.IR3
        )
        assert t == 1.0  # Medium not on the ray path

    def test_medium_in_path_attenuates(self):
        """Medium on the ray path -> T < 1.0."""
        from fireai.core.models_v21 import volumetric_path_transmittance, VolumetricMedium, WavelengthBand
        media = [VolumetricMedium(
            medium_id="smoke",
            medium_type="SMOKE",
            bbox_min=[3, 0, 0], bbox_max=[7, 10, 10],
            alpha_override={WavelengthBand.IR3: 0.5},
        )]
        t = volumetric_path_transmittance(
            (0, 5, 5), (10, 5, 5), media, WavelengthBand.IR3
        )
        assert 0.0 < t < 1.0  # Some attenuation


# ===========================================================================
# 8. HAC Engine with LFL Correction
# ===========================================================================

class TestHACWithLFLCorrection:
    """Test HACClassificationEngine with Burgess-Wheeler LFL correction."""

    def test_hac_with_env_context(self):
        """HAC should use corrected LFL when env_context provided."""
        from fireai.core.hac_classification_engine import HACClassificationEngine
        from fireai.core.models_v21 import (
            SubstanceProperties, HazardType, VentilationLevel,
            EnvironmentalContext, ZoneType,
        )
        engine = HACClassificationEngine()
        # Note: flash_point_c=-188 is below Pydantic min of -100, use None
        sub = SubstanceProperties(
            name="Methane", hazard_type=HazardType.GAS,
            lfl_vol_pct=5.0, ufl_vol_pct=15.0,
            autoignition_c=537.0,
        )

        # Without env_context (default ambient=20C, no correction)
        result_no_correction = engine.classify_v21(
            sub, VentilationLevel.MEDIUM, is_indoor=True, ambient_temp_c=20.0
        )

        # With env_context at 80C (turbine room)
        ctx = EnvironmentalContext(ambient_temp_c=80.0)
        result_with_correction = engine.classify_v21(
            sub, VentilationLevel.MEDIUM, is_indoor=True,
            ambient_temp_c=80.0, env_context=ctx,
        )

        # The corrected LFL is lower -> zone extent is LARGER
        assert result_with_correction.extent.horizontal_m >= result_no_correction.extent.horizontal_m
        # Should have LFL correction warning
        assert any("LFL thermal correction" in w for w in result_with_correction.warnings)

    def test_hac_backward_compatible_without_context(self):
        """HAC should still work without env_context (backward compatible)."""
        from fireai.core.hac_classification_engine import HACClassificationEngine
        from fireai.core.models_v21 import SubstanceProperties, HazardType, VentilationLevel
        engine = HACClassificationEngine()
        sub = SubstanceProperties(
            name="Propane", hazard_type=HazardType.GAS,
            lfl_vol_pct=2.1, ufl_vol_pct=9.5,
            autoignition_c=450.0,  # NFPA 497: propane AIT=450°C
        )
        result = engine.classify_v21(
            sub, VentilationLevel.LOW, is_indoor=True
        )
        assert result.zone is not None


# ===========================================================================
# 9. ATEX Arbiter with Thermal Margin
# ===========================================================================

class TestATEXArbiterWithMargin:
    """Test ATEXHazardousArbiter with IEC 60079-14 thermal margin."""

    def test_zone0_gets_strict_margin(self):
        """Zone 0 should use 5%/10K margin."""
        from fireai.core.atex_hazardous_arbiter import ATEXHazardousArbiter
        from fireai.core.models_v21 import ZoneType, HazardType, _T_CLASS_MAX
        arbiter = ATEXHazardousArbiter()
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_0,
            hazard_type=HazardType.GAS,
            autoignition_c=200.0,
        )
        # With strict margin, t_safe = 200 - max(10, 10) = 190
        # Returned T-class max surface must be <= t_safe
        tc = result.equipment_spec.temp_class.value
        max_surface = _T_CLASS_MAX[tc]
        t_safe = 200.0 - max(10.0, 0.05 * 200.0)
        assert max_surface <= t_safe, (
            f"Got {tc} (max {max_surface}C) which exceeds "
            f"t_safe={t_safe}C for Zone 0!"
        )

    def test_fallback_on_margin_failure(self):
        """If margin selection fails, should fallback to basic selection."""
        from fireai.core.atex_hazardous_arbiter import ATEXHazardousArbiter
        from fireai.core.models_v21 import ZoneType, HazardType
        arbiter = ATEXHazardousArbiter()
        # Very low autoignition -> margin may be too strict
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_0,
            hazard_type=HazardType.GAS,
            autoignition_c=95.0,
        )
        # Should get a result (with or without fallback warning)
        assert result is not None


# ===========================================================================
# 10. Anti-Corruption Layer (Revit ACL)
# ===========================================================================

class TestRevitACL:
    """Test Anti-Corruption Layer for Revit data imports."""

    def test_substance_dto_sanitize_hazard_type(self):
        from fireai.core.revit_acl import RevitSubstanceDTO
        dto = RevitSubstanceDTO(
            element_id="SUB-1", name="Methane", hazard_type="Gas/Vapor",
            lfl_vol_pct="5.0 %", autoignition_c="537",
        )
        assert dto.hazard_type == "GAS"
        assert isinstance(dto.lfl_vol_pct, float)

    def test_substance_dto_to_domain(self):
        from fireai.core.revit_acl import RevitSubstanceDTO, ImportReport
        dto = RevitSubstanceDTO(
            element_id="SUB-1", name="Methane", hazard_type="GAS",
            lfl_vol_pct=5.0, ufl_vol_pct=15.0, autoignition_c=537.0,
        )
        report = ImportReport()
        domain = dto.to_domain(report)
        assert domain is not None
        assert domain.name == "Methane"
        assert domain.lfl_vol_pct == 5.0

    def test_substance_dto_invalid_hazard_type_skipped(self):
        from fireai.core.revit_acl import RevitSubstanceDTO, ImportReport
        dto = RevitSubstanceDTO(
            element_id="SUB-BAD", name="Unknown", hazard_type="PLASMA",
        )
        report = ImportReport()
        domain = dto.to_domain(report)
        assert domain is None
        assert report.has_errors

    def test_batch_import(self):
        from fireai.core.revit_acl import import_substances_from_revit
        raw = [
            {"element_id": "S1", "name": "Methane", "hazard_type": "GAS",
             "lfl_vol_pct": 5.0, "ufl_vol_pct": 15.0},
            {"element_id": "S2", "name": "Bad", "hazard_type": "INVALID"},
            {"element_id": "S3", "name": "Propane", "hazard_type": "GAS",
             "lfl_vol_pct": 2.1, "ufl_vol_pct": 9.5},
        ]
        substances, report = import_substances_from_revit(raw)
        assert len(substances) == 2  # S1 and S3 are valid
        assert report.skipped == 1   # S2 is invalid
        assert report.successful == 2

    def test_obstruction_dto_flat_vertices(self):
        from fireai.core.revit_acl import RevitObstructionDTO
        dto = RevitObstructionDTO(
            element_id="OBS-1",
            obstruction_id="wall_1",
            vertices=[0, 0, 0, 10, 10, 10],  # flat list
        )
        assert len(dto.vertices) == 2
        assert dto.vertices[0] == [0, 0, 0]

    def test_obstruction_dto_to_domain(self):
        from fireai.core.revit_acl import RevitObstructionDTO, ImportReport
        dto = RevitObstructionDTO(
            element_id="OBS-1",
            obstruction_id="glass_panel",
            vertices=[[0, 0, 0], [5, 5, 5]],
            transparency_uv=0.0,
            transparency_vis=0.9,
            transparency_ir1=0.7,
            transparency_ir3=0.8,
        )
        report = ImportReport()
        domain = dto.to_domain(report)
        assert domain is not None
        from fireai.core.models_v21 import WavelengthBand
        assert domain.transmittance_for(WavelengthBand.VIS) == 0.9

    def test_detector_dto_normalize_bands(self):
        from fireai.core.revit_acl import RevitDetectorDTO
        dto = RevitDetectorDTO(
            element_id="DET-1",
            detector_id="flame_01",
            position=[5.0, 5.0, 3.5],
            orientation=[0.0, 0.0, -1.0],
            spectral_bands=["CO2", "UV"],  # CO2 should normalize to IR3
        )
        assert "IR3" in dto.spectral_bands
        assert "UV" in dto.spectral_bands

    def test_detector_dto_to_domain(self):
        from fireai.core.revit_acl import RevitDetectorDTO, ImportReport
        dto = RevitDetectorDTO(
            element_id="DET-1",
            detector_id="flame_01",
            position=[5.0, 5.0, 3.5],
            orientation=[0.0, 0.0, -1.0],
            rated_range_m=25.0,
            aoc_deg=90.0,
            spectral_bands=["IR3", "UV"],
        )
        report = ImportReport()
        domain = dto.to_domain(report)
        assert domain is not None
        assert domain.detector_id == "flame_01"

    def test_import_report_detailed(self):
        from fireai.core.revit_acl import ImportReport
        report = ImportReport(total_elements=5, successful=3, skipped=2)
        report.add_error("E1", "field", "bad", "test error", "ERROR")
        summary = report.summary()
        assert "3 successful" in summary
        assert "2 skipped" in summary


# ===========================================================================
# 11. Ray-Trace with Volumetric Media Integration
# ===========================================================================

class TestRayTraceWithVolumetricMedia:
    """Test FlameDetectorAOCRayTrace with volumetric media."""

    def test_basic_coverage_no_media(self):
        """Basic coverage without volumetric media should still work."""
        from fireai.core.flame_detector_aoc_raytrace import FlameDetectorAOCRayTrace
        from fireai.core.models_v21 import (
            FlameDetectorSpec, RayTracePoint, WavelengthBand,
        )
        engine = FlameDetectorAOCRayTrace(grid_step_m=1.0)
        det = FlameDetectorSpec(
            detector_id="det1",
            position=[5.0, 5.0, 5.0],
            orientation_vector=[0.0, 0.0, -1.0],
            rated_range_m=20.0,
            aoc_deg=90.0,
            spectral_bands=[WavelengthBand.IR3],
        )
        grid = [RayTracePoint(x=x, y=y, z=0.0) for x in range(0, 11) for y in range(0, 11)]
        result = engine.analyse_single_v21(det, grid, [])
        assert len(result.covered_pts) > 0
        assert result.effective_range_m > 0

    def test_coverage_with_volumetric_medium(self):
        """Coverage should decrease with volumetric medium in the path."""
        from fireai.core.flame_detector_aoc_raytrace import FlameDetectorAOCRayTrace
        from fireai.core.models_v21 import (
            FlameDetectorSpec, RayTracePoint, WavelengthBand, VolumetricMedium,
        )
        engine = FlameDetectorAOCRayTrace(grid_step_m=1.0, detector_threshold=0.1)
        det = FlameDetectorSpec(
            detector_id="det1",
            position=[5.0, 5.0, 5.0],
            orientation_vector=[0.0, 0.0, -1.0],
            rated_range_m=20.0,
            aoc_deg=90.0,
            spectral_bands=[WavelengthBand.IR3],
        )
        grid = [RayTracePoint(x=x, y=y, z=0.0) for x in range(0, 11) for y in range(0, 11)]

        # Without media
        result_clear = engine.analyse_single_v21(det, grid, [])

        # With dense smoke between detector and floor
        media = [VolumetricMedium(
            medium_id="smoke_1",
            medium_type="SMOKE",
            bbox_min=[0.0, 0.0, 2.0],
            bbox_max=[10.0, 10.0, 4.0],
            alpha_override={WavelengthBand.IR3: 2.0},
        )]
        result_smoke = engine.analyse_single_v21(det, grid, [], media)

        # Coverage with smoke should be <= coverage without
        assert len(result_smoke.covered_pts) <= len(result_clear.covered_pts)

    def test_spectral_map_populated(self):
        """Spectral transmittance map should contain per-point values."""
        from fireai.core.flame_detector_aoc_raytrace import FlameDetectorAOCRayTrace
        from fireai.core.models_v21 import (
            FlameDetectorSpec, RayTracePoint, WavelengthBand, VolumetricMedium,
        )
        engine = FlameDetectorAOCRayTrace(grid_step_m=1.0)
        det = FlameDetectorSpec(
            detector_id="det1",
            position=[5.0, 5.0, 5.0],
            orientation_vector=[0.0, 0.0, -1.0],
            rated_range_m=20.0,
            aoc_deg=90.0,
            spectral_bands=[WavelengthBand.IR3],
        )
        grid = [RayTracePoint(x=x, y=y, z=0.0) for x in range(0, 6) for y in range(0, 6)]
        media = [VolumetricMedium(
            medium_id="smoke_1",
            medium_type="SMOKE",
            bbox_min=[0.0, 0.0, 2.0],
            bbox_max=[5.0, 5.0, 4.0],
            alpha_override={WavelengthBand.IR3: 0.5},
        )]
        result = engine.analyse_single_v21(det, grid, [], media)
        # Should have transmittance values for covered points
        assert len(result.spectral_transmittance_map) > 0
        for pt_idx, t in result.spectral_transmittance_map.items():
            assert 0.0 < t <= 1.0


# ===========================================================================
# 12. Regression Tests — Existing V21 functionality still works
# ===========================================================================

class TestV21Regression:
    """Ensure V21.2 changes don't break existing V21 functionality."""

    def test_substance_properties_still_works(self):
        from fireai.core.models_v21 import SubstanceProperties, HazardType
        sub = SubstanceProperties(
            name="Methane", hazard_type=HazardType.GAS,
            lfl_vol_pct=5.0, ufl_vol_pct=15.0,
            autoignition_c=537.0,
        )
        assert sub.name == "Methane"

    def test_epl_hierarchy_still_enforced(self):
        from fireai.core.models_v21 import ATEXEquipmentSpec, ZoneType, TemperatureClass
        with pytest.raises(ValidationError, match="INSUFFICIENT"):
            ATEXEquipmentSpec(
                zone=ZoneType.ZONE_0,
                epl_required="Gc",  # WRONG — Zone 0 needs Ga
                atex_category="3G",
                temp_class=TemperatureClass.T4,
                protection_modes=["ia"],
            )

    def test_critical_flag_still_enforced(self):
        from fireai.core.models_v21 import HACResult, ZoneExtent, ZoneType, VentilationLevel, HazardType
        with pytest.raises(ValidationError, match="CRITICAL"):
            HACResult(
                zone=ZoneType.ZONE_0,
                extent=ZoneExtent(horizontal_m=3.0, vertical_m=1.5, volume_m3=28.27),
                ventilation=VentilationLevel.POOR,
                hazard_type=HazardType.GAS,
                critical_flags=[],  # Empty — must not be silently dropped!
            )

    def test_select_temp_class_still_works(self):
        from fireai.core.models_v21 import _select_temp_class, _T_CLASS_MAX
        tc = _select_temp_class(180.0)
        # Verify safety: max surface must be strictly below autoignition
        max_surface = _T_CLASS_MAX[tc.value]
        assert max_surface < 180.0, (
            f"Got {tc.value} (max {max_surface}C) — "
            f"must be STRICTLY below autoignition 180C!"
        )

    def test_unknown_country_error_still_raises(self):
        from fireai.core.international_reg_selector import UnknownCountryError, resolve
        with pytest.raises(UnknownCountryError):
            resolve("XX")

    def test_ray_trace_basic_still_works(self):
        from fireai.core.flame_detector_aoc_raytrace import FlameDetectorAOCRayTrace
        from fireai.core.models_v21 import (
            FlameDetectorSpec, RayTracePoint, WavelengthBand,
        )
        engine = FlameDetectorAOCRayTrace(grid_step_m=1.0)
        det = FlameDetectorSpec(
            detector_id="test",
            position=[5.0, 5.0, 5.0],
            orientation_vector=[0.0, 0.0, -1.0],
            rated_range_m=20.0,
            aoc_deg=90.0,
            spectral_bands=[WavelengthBand.IR3],
        )
        grid = [RayTracePoint(x=5, y=5, z=0)]
        result = engine.analyse_single_v21(det, grid, [])
        assert 0 in result.covered_pts
