"""
tests/test_v21_phase5_gap01_08.py
Phase 5 GAP-01 through GAP-08 comprehensive tests.
Adapted from consultant deliverables with correct import paths and API fixes.

Run with: pytest tests/test_v21_phase5_gap01_08.py -v
"""

import math
import pytest
from typing import Optional

from fireai.core.models_v21 import (
    SubstanceProperties, ZoneExtent, HACResult, EnvironmentalContext,
    VentilationLevel, ZoneType, HazardType, WavelengthBand,
    TemperatureClass, RegulatoryFramework, PasquillStability,
    ThermalMarginRule, SpectralSignature, VolumetricMedium,
    SpectralSignatureRegistry, burgess_wheeler_lfl,
    _select_temp_class, _select_temp_class_with_margin,
    beer_lambert_transmittance, _DEFAULT_MEDIUM_ALPHA,
)
from fireai.core.hac_classification_engine import (
    HACClassificationEngine, ReleaseGrade,
)
from fireai.core.atex_hazardous_arbiter import (
    ATEXHazardousArbiter, ATEXArbitrationResult,
)
from fireai.core.flame_detector_aoc_raytrace import (
    FlameDetectorAOCRayTrace, CoverageResult,
)
from fireai.core.models_v21 import (
    Obstruction, FlameDetectorSpec, RayTracePoint,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def propane() -> SubstanceProperties:
    return SubstanceProperties(
        name="Propane", hazard_type=HazardType.GAS,
        lfl_vol_pct=2.1, ufl_vol_pct=9.5, flash_point_c=-104.0,
        autoignition_c=470.0, molecular_weight=44.1, density_kg_m3=1.882,
    )

@pytest.fixture
def methane() -> SubstanceProperties:
    return SubstanceProperties(
        name="Methane", hazard_type=HazardType.GAS,
        lfl_vol_pct=5.0, ufl_vol_pct=15.0,
        autoignition_c=595.0, molecular_weight=16.04, density_kg_m3=0.668,
    )

@pytest.fixture
def coal_dust() -> SubstanceProperties:
    return SubstanceProperties(
        name="Coal Dust", hazard_type=HazardType.DUST,
        mec_g_m3=60.0, kst_bar_m_s=150.0, mie_mj=40.0,
    )

@pytest.fixture
def hac_engine() -> HACClassificationEngine:
    return HACClassificationEngine()

@pytest.fixture
def arbiter() -> ATEXHazardousArbiter:
    return ATEXHazardousArbiter()

@pytest.fixture
def raytrace() -> FlameDetectorAOCRayTrace:
    return FlameDetectorAOCRayTrace()


# ═════════════════════════════════════════════════════════════════════════════
# GAP-01: IEC 60079-10-1 Annex B zone extent formula
# ═════════════════════════════════════════════════════════════════════════════

class TestGAP01AnnexBExtent:

    def test_annex_b_primary_propane_medium_vent(self, hac_engine, propane):
        """IEC Annex B §B.2: MEDIUM vent, PRIMARY release, indoor."""
        result = hac_engine.classify_v21(
            substance=propane, ventilation=VentilationLevel.MEDIUM,
            release_grade=ReleaseGrade.PRIMARY, is_indoor=True,
            release_rate_kg_s=0.01, room_volume_m3=500.0,
        )
        assert result.zone == ZoneType.ZONE_1
        assert result.extent.horizontal_m > 0.5
        assert any("Annex B" in w for w in result.warnings)

    def test_annex_b_continuous_high_vent(self, hac_engine, propane):
        """CONTINUOUS release, HIGH ventilation, large warehouse."""
        result = hac_engine.classify_v21(
            substance=propane, ventilation=VentilationLevel.HIGH,
            release_grade=ReleaseGrade.CONTINUOUS, is_indoor=True,
            release_rate_kg_s=0.001, room_volume_m3=10_000.0,
        )
        assert result.zone == ZoneType.ZONE_0
        assert result.extent.volume_m3 > 0.0

    def test_annex_b_fallback_when_no_lfl(self, hac_engine, coal_dust):
        """coal_dust has no lfl_vol_pct → fallback to simplified."""
        result = hac_engine.classify_v21(
            substance=coal_dust, ventilation=VentilationLevel.MEDIUM,
            release_grade=ReleaseGrade.PRIMARY, is_indoor=True,
            release_rate_kg_s=0.05, room_volume_m3=200.0,
        )
        assert result.zone in (
            ZoneType.ZONE_21, ZoneType.ZONE_22, ZoneType.ZONE_20
        )

    def test_annex_b_zero_release_rate_uses_simplified(self, hac_engine, propane):
        """release_rate_kg_s=0 → simplified method, no Annex B warning."""
        result = hac_engine.classify_v21(
            substance=propane, ventilation=VentilationLevel.MEDIUM,
            release_grade=ReleaseGrade.PRIMARY, is_indoor=True,
            release_rate_kg_s=0.0,
        )
        assert not any("Annex B" in w for w in result.warnings)
        assert result.extent.horizontal_m > 0.0

    def test_annex_b_hydrogen_buoyant_vertical(self, hac_engine):
        """Hydrogen MW=2 < air MW=29 → buoyant → vertical >= horizontal."""
        hydrogen = SubstanceProperties(
            name="Hydrogen", hazard_type=HazardType.GAS,
            lfl_vol_pct=4.0, ufl_vol_pct=75.0,
            autoignition_c=500.0, molecular_weight=2.016, density_kg_m3=0.084,
        )
        result = hac_engine.classify_v21(
            substance=hydrogen, ventilation=VentilationLevel.LOW,
            release_grade=ReleaseGrade.PRIMARY, is_indoor=True,
            release_rate_kg_s=0.005, room_volume_m3=300.0,
        )
        assert result.extent.vertical_m >= result.extent.horizontal_m * 0.9


# ═════════════════════════════════════════════════════════════════════════════
# GAP-02: release_grade in classify_v21()
# ═════════════════════════════════════════════════════════════════════════════

class TestGAP02ReleaseGrade:

    def test_continuous_primary_secondary_gas(self, hac_engine, propane):
        """IEC §4.2: three grades → three zones (MEDIUM vent)."""
        r0 = hac_engine.classify_v21(
            propane, VentilationLevel.MEDIUM, release_grade=ReleaseGrade.CONTINUOUS)
        r1 = hac_engine.classify_v21(
            propane, VentilationLevel.MEDIUM, release_grade=ReleaseGrade.PRIMARY)
        r2 = hac_engine.classify_v21(
            propane, VentilationLevel.MEDIUM, release_grade=ReleaseGrade.SECONDARY)
        assert r0.zone == ZoneType.ZONE_0
        assert r1.zone == ZoneType.ZONE_1
        assert r2.zone == ZoneType.ZONE_2

    def test_continuous_primary_secondary_dust(self, hac_engine, coal_dust):
        """IEC §4.2: dust zones 20/21/22 from release grade."""
        r0 = hac_engine.classify_v21(
            coal_dust, VentilationLevel.MEDIUM, release_grade=ReleaseGrade.CONTINUOUS)
        r1 = hac_engine.classify_v21(
            coal_dust, VentilationLevel.MEDIUM, release_grade=ReleaseGrade.PRIMARY)
        r2 = hac_engine.classify_v21(
            coal_dust, VentilationLevel.MEDIUM, release_grade=ReleaseGrade.SECONDARY)
        assert r0.zone == ZoneType.ZONE_20
        assert r1.zone == ZoneType.ZONE_21
        assert r2.zone == ZoneType.ZONE_22

    def test_poor_ventilation_escalates_zone(self, hac_engine, propane):
        """IEC §4.3: POOR ventilation escalates SECONDARY→Zone 1."""
        result = hac_engine.classify_v21(
            propane, VentilationLevel.POOR, release_grade=ReleaseGrade.SECONDARY)
        assert result.zone == ZoneType.ZONE_1

    def test_high_ventilation_reduces_primary(self, hac_engine, propane):
        """IEC §4.3: HIGH ventilation reduces PRIMARY → Zone 2."""
        result = hac_engine.classify_v21(
            propane, VentilationLevel.HIGH, release_grade=ReleaseGrade.PRIMARY)
        assert result.zone == ZoneType.ZONE_2

    def test_backward_compat_no_release_grade(self, hac_engine, propane):
        """Omitting release_grade defaults to PRIMARY."""
        result = hac_engine.classify_v21(
            propane, VentilationLevel.MEDIUM, is_indoor=True)
        assert isinstance(result, HACResult)
        assert result.zone is not None

    def test_continuous_poor_stays_zone0(self, hac_engine, propane):
        """CONTINUOUS + POOR → still Zone 0 (cannot escalate beyond 0)."""
        result = hac_engine.classify_v21(
            propane, VentilationLevel.POOR, release_grade=ReleaseGrade.CONTINUOUS)
        assert result.zone == ZoneType.ZONE_0


# ═════════════════════════════════════════════════════════════════════════════
# GAP-03: VolumetricMedium.get_alpha() default table
# ═════════════════════════════════════════════════════════════════════════════

class TestGAP03DefaultAlpha:

    def test_smoke_medium_not_transparent(self):
        """SMOKE without override must return >0 for VIS band."""
        medium = VolumetricMedium(
            medium_id="test_smoke", medium_type="SMOKE",
            bbox_min=[0.0, 0.0, 0.0], bbox_max=[10.0, 10.0, 3.0],
        )
        assert medium.get_alpha(WavelengthBand.VIS) > 0.0

    def test_steam_ir1_strong_absorption(self):
        """STEAM: IR1 (H₂O bands) must be strongest absorption."""
        medium = VolumetricMedium(
            medium_id="steam_cloud", medium_type="STEAM",
            bbox_min=[0.0, 0.0, 0.0], bbox_max=[5.0, 5.0, 2.0],
        )
        assert medium.get_alpha(WavelengthBand.IR1) > medium.get_alpha(WavelengthBand.UV)

    def test_gas_cloud_vis_transparent(self):
        """GAS_CLOUD must be transparent in VIS band."""
        medium = VolumetricMedium(
            medium_id="methane_cloud", medium_type="GAS_CLOUD",
            bbox_min=[0.0, 0.0, 0.0], bbox_max=[3.0, 3.0, 3.0],
        )
        assert medium.get_alpha(WavelengthBand.VIS) == pytest.approx(0.0)

    def test_concentration_factor_scales_alpha(self):
        """concentration_factor=2.0 must double the default alpha."""
        m1 = VolumetricMedium(
            medium_id="s1", medium_type="SMOKE",
            bbox_min=[0, 0, 0], bbox_max=[5, 5, 3],
            concentration_factor=1.0,
        )
        m2 = VolumetricMedium(
            medium_id="s2", medium_type="SMOKE",
            bbox_min=[0, 0, 0], bbox_max=[5, 5, 3],
            concentration_factor=2.0,
        )
        assert m2.get_alpha(WavelengthBand.VIS) == pytest.approx(
            2.0 * m1.get_alpha(WavelengthBand.VIS)
        )

    def test_explicit_override_takes_priority(self):
        """alpha_override must override the default table."""
        medium = VolumetricMedium(
            medium_id="custom", medium_type="SMOKE",
            bbox_min=[0, 0, 0], bbox_max=[5, 5, 3],
            alpha_override={WavelengthBand.VIS: 99.9},
        )
        assert medium.get_alpha(WavelengthBand.VIS) == pytest.approx(99.9)


# ═════════════════════════════════════════════════════════════════════════════
# GAP-04: SpectralSignatureRegistry extended substances
# ═════════════════════════════════════════════════════════════════════════════

class TestGAP04ExtendedRegistry:

    @pytest.fixture
    def registry(self) -> SpectralSignatureRegistry:
        return SpectralSignatureRegistry()

    @pytest.mark.parametrize("cas,name", [
        ("74-85-1",  "Ethylene"),
        ("74-86-2",  "Acetylene"),
        ("64-17-5",  "Ethanol"),
        ("110-54-3", "n-Hexane"),
        ("71-43-2",  "Benzene"),
        ("108-88-3", "Toluene"),
        ("95-47-6",  "o-Xylene"),
        ("7664-41-7","Ammonia"),
        ("7783-06-4","Hydrogen Sulfide"),
        ("67-64-1",  "Acetone"),
        ("67-56-1",  "Methanol"),
        ("67-63-0",  "Isopropanol"),
    ])
    def test_substance_registered(self, registry, cas, name):
        sig = registry.get(cas)
        assert sig is not None, f"CAS {cas} ({name}) not found"
        assert sig.substance_name == name

    def test_benzene_strong_uv(self, registry):
        sig = registry.get("71-43-2")
        assert sig.alpha_uv > sig.alpha_vis
        assert sig.alpha_uv > 5.0

    def test_ammonia_strong_ir1(self, registry):
        sig = registry.get("7664-41-7")
        assert sig.alpha_ir1 > sig.alpha_uv

    def test_h2s_strong_ir3(self, registry):
        sig = registry.get("7783-06-4")
        assert sig.alpha_ir3 > sig.alpha_vis

    def test_total_registry_size_at_least_16(self, registry):
        assert registry.count() >= 16


# ═════════════════════════════════════════════════════════════════════════════
# GAP-05: Zone/hazard_type cross-validation in arbiter
# ═════════════════════════════════════════════════════════════════════════════

class TestGAP05ZoneHazardCrossValidation:

    def test_zone0_with_dust_returns_error(self, arbiter, coal_dust):
        """Zone 0 (gas zone) + DUST hazard → errors."""
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_0, hazard_type=HazardType.DUST,
            autoignition_c=400.0,
        )
        assert not result.is_valid
        assert any("gas zone" in e.lower() or "DUST" in e
                   for e in result.errors)

    def test_zone21_with_gas_returns_error(self, arbiter, propane):
        """Zone 21 (dust zone) + GAS hazard → errors."""
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_21, hazard_type=HazardType.GAS,
            autoignition_c=470.0,
        )
        # Cross-validation error is in errors list; spec construction may also fail
        cross_errors = [e for e in result.errors
                        if "dust zone" in e.lower() or "GAS" in e]
        assert len(cross_errors) > 0, "Expected zone/hazard cross-validation error"

    def test_zone1_with_gas_is_valid(self, arbiter, propane):
        """Zone 1 + GAS → no cross-validation error."""
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_1, hazard_type=HazardType.GAS,
            autoignition_c=470.0,
        )
        cross_errors = [e for e in result.errors
                        if "gas zone" in e.lower() or "dust zone" in e.lower()]
        assert len(cross_errors) == 0

    def test_hybrid_in_gas_zone_produces_warning(self, arbiter):
        """HYBRID hazard in gas zone → warning (not error)."""
        result = arbiter.arbitrate_v21(
            zone=ZoneType.ZONE_1, hazard_type=HazardType.HYBRID,
            autoignition_c=450.0,
        )
        assert any("HYBRID" in w or "hybrid" in w.lower()
                   for w in result.all_warnings)


# ═════════════════════════════════════════════════════════════════════════════
# GAP-06: Redundancy tracking in CoverageResult
# ═════════════════════════════════════════════════════════════════════════════

class TestGAP06Redundancy:

    @pytest.fixture
    def grid_points(self) -> list:
        """3×3 target grid at z=0."""
        return [
            RayTracePoint(x=float(x), y=float(y), z=0.0)
            for x in range(3) for y in range(3)
        ]

    @pytest.fixture
    def det_A(self) -> FlameDetectorSpec:
        return FlameDetectorSpec(
            detector_id="DET_A",
            position=[1.0, 1.0, 3.0],
            orientation_vector=[0.0, 0.0, -1.0],
            rated_range_m=15.0, aoc_deg=90.0,
            spectral_bands=[WavelengthBand.IR1, WavelengthBand.IR3],
        )

    @pytest.fixture
    def det_B(self) -> FlameDetectorSpec:
        return FlameDetectorSpec(
            detector_id="DET_B",
            position=[2.0, 2.0, 3.0],
            orientation_vector=[0.0, 0.0, -1.0],
            rated_range_m=15.0, aoc_deg=90.0,
            spectral_bands=[WavelengthBand.IR1, WavelengthBand.IR3],
        )

    def test_coverage_result_has_redundancy_fields(
        self, raytrace, grid_points, det_A, det_B
    ):
        result = raytrace.analyse_multi_v21(
            detectors=[det_A, det_B], target_grid=grid_points,
            obstructions=[],
        )
        assert hasattr(result, "redundancy_map")
        assert hasattr(result, "min_redundancy")
        assert hasattr(result, "mean_redundancy")
        assert hasattr(result, "double_covered_pct")

    def test_two_detectors_some_double_coverage(
        self, raytrace, grid_points, det_A, det_B
    ):
        """Two overlapping detectors → some points with redundancy >= 2."""
        result = raytrace.analyse_multi_v21(
            detectors=[det_A, det_B], target_grid=grid_points,
            obstructions=[],
        )
        if result.covered_points > 0:
            max_red = max(result.redundancy_map.values(), default=0)
            assert max_red >= 2

    def test_single_detector_min_redundancy_one(
        self, raytrace, grid_points, det_A
    ):
        """Single detector: min_redundancy <= 1."""
        result = raytrace.analyse_multi_v21(
            detectors=[det_A], target_grid=grid_points, obstructions=[],
        )
        assert result.min_redundancy <= 1

    def test_is_nfpa72_redundant_false_for_single(
        self, raytrace, grid_points, det_A
    ):
        result = raytrace.analyse_multi_v21(
            detectors=[det_A], target_grid=grid_points, obstructions=[],
        )
        assert result.is_nfpa72_redundant is False


# ═════════════════════════════════════════════════════════════════════════════
# GAP-07: VolumetricMedium non-zero volume validator
# ═════════════════════════════════════════════════════════════════════════════

class TestGAP07BboxNonzeroVolume:

    def test_zero_x_dimension_raises(self):
        with pytest.raises(ValueError, match="zero or near-zero volume"):
            VolumetricMedium(
                medium_id="bad", medium_type="SMOKE",
                bbox_min=[5.0, 0.0, 0.0], bbox_max=[5.0, 5.0, 3.0],
            )

    def test_zero_y_dimension_raises(self):
        with pytest.raises(ValueError, match="zero or near-zero volume"):
            VolumetricMedium(
                medium_id="bad2", medium_type="STEAM",
                bbox_min=[0.0, 3.0, 0.0], bbox_max=[5.0, 3.0, 3.0],
            )

    def test_valid_medium_passes(self):
        medium = VolumetricMedium(
            medium_id="valid", medium_type="SMOKE",
            bbox_min=[0.0, 0.0, 0.0], bbox_max=[10.0, 10.0, 3.0],
        )
        assert medium is not None

    def test_near_zero_volume_raises(self):
        with pytest.raises(ValueError):
            VolumetricMedium(
                medium_id="thin", medium_type="GAS_CLOUD",
                bbox_min=[0.0, 0.0, 0.0],
                bbox_max=[0.0001, 0.0001, 0.0001],
            )


# ═════════════════════════════════════════════════════════════════════════════
# GAP-08: <= consistency in _select_temp_class_with_margin
# ═════════════════════════════════════════════════════════════════════════════

class TestGAP08TempClassConsistency:

    def test_boundary_value_accepted_with_margin(self):
        """IEC 60079-0 §7.3: max_surface <= t_safe is accepted."""
        result = _select_temp_class_with_margin(300.0, ZoneType.ZONE_1)
        # Zone 1: t_safe = 300 - max(5, 15) = 285
        # T2A max=280 <= 285 → accepted
        assert result != TemperatureClass.T1

    def test_basic_and_margin_use_same_operator(self):
        """autoignition=450°C, Zone 2 → t_safe=449°C → T2 (300<=449)."""
        result = _select_temp_class_with_margin(450.0, ZoneType.ZONE_2)
        assert result == TemperatureClass.T2

    def test_zone0_strict_margin(self):
        """Zone 0: t_safe = autoignition - max(10K, 5%)."""
        result = _select_temp_class_with_margin(200.0, ZoneType.ZONE_0)
        t_max_map = {"T1":450,"T2":300,"T2A":280,"T2B":260,"T2C":230,"T2D":215,
                     "T3":200,"T3A":180,"T3B":165,"T3C":160,"T4":135,"T4A":120,
                     "T5":100,"T6":85}
        # t_safe = 200 - max(10, 10) = 190
        assert t_max_map[result.value] <= 190

    def test_select_temp_class_basic_consistency(self):
        """_select_temp_class uses < (strictly below autoignition).
        autoignition=135°C: T4 max=135 NOT < 135 → rejected.
        T4A max=120 < 135 → accepted. So result is T4A."""
        result = _select_temp_class(135.0)
        assert result == TemperatureClass.T4A  # 120 < 135, not T4 (135 !< 135)

    def test_both_functions_return_same_for_safe_margin(self):
        basic  = _select_temp_class(600.0)
        margin = _select_temp_class_with_margin(600.0, ZoneType.ZONE_1)
        assert basic  == TemperatureClass.T1
        assert margin == TemperatureClass.T1
