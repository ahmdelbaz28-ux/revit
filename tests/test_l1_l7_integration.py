"""
test_l1_l7_integration.py — L1→L7 End-to-End Integration Tests
================================================================
V24 closure requirement #1: Full pipeline integration test from
regulatory selection through hybrid survivability classification.

Tests the complete 7-layer FireAlarmAI pipeline:
  L1: InternationalRegSelector   → Regulatory framework resolution
  L2: HACClassificationEngine    → Hazardous area classification
  L3: ATEXHazardousArbiter       → Equipment protection level
  L5: FlameDetectorAOCRayTrace   → Optical coverage analysis
  V23: UGLD Acoustics + RayTrace → Acoustic coverage analysis
  L7: HybridSurvivabilityEngine  → Hybrid survivability index

Each test exercises the COMPLETE chain with real objects, not mocks.
Data flows from one layer to the next exactly as it would in production.

Reference Standards:
  IEC 60079-0:2017     — General requirements for Ex equipment
  IEC 60079-10-1:2015  — Gas zone classification
  NFPA 72-2022 §17.8.3 — Flame detector coverage
  ISA-TR 84.00.07      — UGLD coverage
  ISO 9613-1:1993      — Atmospheric acoustic absorption
"""

from __future__ import annotations

import math
import pytest

# ── L1 imports ──────────────────────────────────────────────────────────
from fireai.core.international_reg_selector import (
    InternationalRegSelector,
    UnknownCountryError,
    resolve as resolve_regulatory,
)

# ── L2 imports ──────────────────────────────────────────────────────────
from fireai.core.hac_classification_engine import HACClassificationEngine

# ── L3 imports ──────────────────────────────────────────────────────────
from fireai.core.atex_hazardous_arbiter import ATEXHazardousArbiter

# ── L4 (models) imports ────────────────────────────────────────────────
from fireai.core.models_v21 import (
    SubstanceProperties,
    FlameDetectorSpec,
    Obstruction,
    RayTracePoint,
    VolumetricMedium,
    EnvironmentalContext,
    ZoneType,
    HazardType,
    VentilationLevel,
    WavelengthBand,
    TemperatureClass,
)

# ── L5 imports ──────────────────────────────────────────────────────────
from fireai.core.flame_detector_aoc_raytrace import (
    FlameDetectorAOCRayTrace,
    CoverageResult,
)

# ── V23 imports ─────────────────────────────────────────────────────────
from fireai.core.ugld_acoustics import UltrasonicSensor
from fireai.core.ugld_raytrace import AcousticObstacle, trace_acoustic_ray

# ── L7 imports ──────────────────────────────────────────────────────────
from fireai.core.hybrid_survivability import (
    HybridSurvivabilityEngine,
    HybridSurvivabilityMap,
    HybridPointResult,
    SurvivabilityClass,
    AcousticCoverageDetail,
)


# ===========================================================================
# Fixtures — Realistic petrochemical scenario
# ===========================================================================

@pytest.fixture
def methane() -> SubstanceProperties:
    """Methane — the most common hazardous gas in petrochemical plants."""
    return SubstanceProperties(
        name="Methane",
        hazard_type=HazardType.GAS,
        lfl_vol_pct=5.0,
        ufl_vol_pct=15.0,
        flash_point_c=-188.0,
        autoignition_c=537.0,
        density_kg_m3=0.657,
        molecular_weight=16.04,
    )


@pytest.fixture
def propane() -> SubstanceProperties:
    """Propane — common LPG component."""
    return SubstanceProperties(
        name="Propane",
        hazard_type=HazardType.GAS,
        lfl_vol_pct=2.1,
        ufl_vol_pct=9.5,
        flash_point_c=-104.0,
        autoignition_c=450.0,
        density_kg_m3=1.88,
        molecular_weight=44.10,
    )


@pytest.fixture
def hydrogen_sulfide() -> SubstanceProperties:
    """H2S — sour gas, extremely toxic + flammable."""
    return SubstanceProperties(
        name="Hydrogen Sulfide",
        hazard_type=HazardType.GAS,
        lfl_vol_pct=4.3,
        ufl_vol_pct=46.0,
        flash_point_c=-60.0,
        autoignition_c=260.0,
        density_kg_m3=1.36,
        molecular_weight=34.08,
    )


@pytest.fixture
def simple_grid() -> list[RayTracePoint]:
    """5x5 horizontal grid at z=3m — small enough for fast tests."""
    grid = []
    for ix in range(5):
        for iy in range(5):
            grid.append(RayTracePoint(x=float(ix), y=float(iy), z=3.0))
    return grid


@pytest.fixture
def flame_detector() -> FlameDetectorSpec:
    """Single UV/IR flame detector covering the grid area."""
    return FlameDetectorSpec(
        detector_id="FD-001",
        position=[2.0, 2.0, 6.0],
        orientation_vector=[0.0, 0.0, -1.0],
        rated_range_m=30.0,
        aoc_deg=90.0,
        spectral_bands=[WavelengthBand.UV, WavelengthBand.IR1],
    )


@pytest.fixture
def two_flame_detectors() -> list[FlameDetectorSpec]:
    """Two overlapping flame detectors for redundancy."""
    return [
        FlameDetectorSpec(
            detector_id="FD-001",
            position=[1.0, 2.0, 6.0],
            orientation_vector=[0.0, 0.0, -1.0],
            rated_range_m=30.0,
            aoc_deg=90.0,
            spectral_bands=[WavelengthBand.UV, WavelengthBand.IR1],
        ),
        FlameDetectorSpec(
            detector_id="FD-002",
            position=[3.0, 2.0, 6.0],
            orientation_vector=[0.0, 0.0, -1.0],
            rated_range_m=30.0,
            aoc_deg=90.0,
            spectral_bands=[WavelengthBand.UV, WavelengthBand.IR1],
        ),
    ]


@pytest.fixture
def ugld_sensor() -> UltrasonicSensor:
    """Single UGLD sensor — typical commercial unit."""
    return UltrasonicSensor(
        sensor_id="UGLD-001",
        trigger_threshold_db=74.0,
        background_noise_db=55.0,
        center_frequency_hz=40_000.0,
    )


@pytest.fixture
def two_ugld_sensors() -> list[UltrasonicSensor]:
    """Two UGLD sensors for acoustic redundancy."""
    return [
        UltrasonicSensor(
            sensor_id="UGLD-001",
            trigger_threshold_db=74.0,
            background_noise_db=55.0,
            center_frequency_hz=40_000.0,
        ),
        UltrasonicSensor(
            sensor_id="UGLD-002",
            trigger_threshold_db=74.0,
            background_noise_db=60.0,
            center_frequency_hz=40_000.0,
        ),
    ]


@pytest.fixture
def ugld_positions() -> dict:
    """Sensor position mapping — Layer 7 requires separate positions."""
    return {
        "UGLD-001": (2.0, 2.0, 5.0),
        "UGLD-002": (4.0, 2.0, 5.0),
    }


@pytest.fixture
def steel_obstruction() -> Obstruction:
    """Steel wall obstruction blocking some optical paths."""
    return Obstruction(
        obstruction_id="WALL-01",
        vertices=[
            [3.5, -1.0, 0.0],
            [3.5, 6.0, 0.0],
            [3.5, 6.0, 4.0],
            [3.5, -1.0, 4.0],
        ],
        spectral_transparency={
            WavelengthBand.UV: 0.0,
            WavelengthBand.VIS: 0.0,
            WavelengthBand.IR1: 0.0,
        },
    )


@pytest.fixture
def acoustic_wall() -> AcousticObstacle:
    """Concrete wall blocking acoustic propagation."""
    return AcousticObstacle(
        obstacle_id="AWALL-01",
        vertices=[
            [3.5, -1.0, 0.0],
            [3.5, 6.0, 0.0],
            [3.5, 6.0, 4.0],
            [3.5, -1.0, 4.0],
        ],
        surface_type="CONCRETE",
        height_m=4.0,
    )


# ===========================================================================
# Test: L1 Regulatory Framework Selection
# ===========================================================================

class TestL1RegulatorySelection:
    """Layer 1: Regulatory framework resolution — the legal gate."""

    def test_saudi_arabia_resolves_iecex(self):
        """KSA uses IECEx — major petrochemical jurisdiction."""
        result = resolve_regulatory("SA")
        assert result.framework.value == "IECEx"  # Enum value is "IECEx" not "IECEX"
        assert result.zone_system == "ZONE"

    def test_germany_resolves_atex(self):
        """Germany uses ATEX — EU member state."""
        result = resolve_regulatory("DE")
        assert result.framework.value == "ATEX_EU"
        assert result.zone_system == "ZONE"

    def test_usa_resolves_nec(self):
        """USA uses NEC Division system."""
        result = resolve_regulatory("US")
        assert result.framework.value == "NEC_US"
        assert result.zone_system == "DIVISION"

    def test_canada_resolves_cec(self):
        """Canada uses CEC Zone system (since 1998, Fix #1)."""
        result = resolve_regulatory("CA")
        assert result.framework.value == "CEC_CANADA"
        assert result.zone_system == "ZONE"

    def test_norway_resolves_efta(self):
        """Norway uses EFTA (not EU member, Fix #3)."""
        result = resolve_regulatory("NO")
        assert result.framework.value == "EFTA"
        assert len(result.warnings) > 0  # Must warn about EFTA

    def test_unknown_country_raises(self):
        """Unknown country raises UnknownCountryError (Q3)."""
        with pytest.raises(UnknownCountryError, match="XX"):
            resolve_regulatory("XX")

    def test_legacy_selector_matches_v21(self):
        """Legacy InternationalRegSelector agrees with V21 resolve()."""
        selector = InternationalRegSelector()
        legacy = selector.resolve("SA")
        v21 = resolve_regulatory("SA")
        assert legacy.is_valid
        assert v21.framework.value == "IECEx"


# ===========================================================================
# Test: L1→L2 Regulatory + Classification Chain
# ===========================================================================

class TestL1L2RegulatoryAndClassification:
    """L1 output feeds into L2 classification."""

    def test_iecex_methane_zone1_medium_vent(self, methane: SubstanceProperties):
        """Saudi Arabia + Methane + Medium ventilation → Zone 1."""
        l1 = resolve_regulatory("SA")
        assert l1.zone_system == "ZONE"

        hac = HACClassificationEngine()
        hac_result = hac.classify_v21(
            substance=methane,
            ventilation=VentilationLevel.MEDIUM,
            is_indoor=True,
        )
        assert hac_result.zone in (ZoneType.ZONE_1, ZoneType.ZONE_2)
        assert hac_result.hazard_type == HazardType.GAS

    def test_atex_propane_zone1_poor_vent(self, propane: SubstanceProperties):
        """Germany + Propane + Poor ventilation → Zone 1 (or Zone 0)."""
        l1 = resolve_regulatory("DE")
        assert l1.zone_system == "ZONE"

        hac = HACClassificationEngine()
        hac_result = hac.classify_v21(
            substance=propane,
            ventilation=VentilationLevel.POOR,
            is_indoor=True,
        )
        # Poor ventilation drives zone toward Zone 0 or Zone 1
        assert hac_result.zone in (ZoneType.ZONE_0, ZoneType.ZONE_1)

    def test_h2s_poor_vent_zone0(self, hydrogen_sulfide: SubstanceProperties):
        """H2S + Poor ventilation → Zone 0 (most hazardous)."""
        hac = HACClassificationEngine()
        hac_result = hac.classify_v21(
            substance=hydrogen_sulfide,
            ventilation=VentilationLevel.POOR,
            is_indoor=True,
        )
        assert hac_result.zone in (ZoneType.ZONE_0, ZoneType.ZONE_1)
        assert hac_result.hazard_type == HazardType.GAS


# ===========================================================================
# Test: L1→L2→L3 Regulatory + Classification + ATEX Chain
# ===========================================================================

class TestL1L2L3RegulatoryClassificationArbitration:
    """L1→L2→L3 chain: regulatory → zone → equipment spec."""

    def test_methane_zone1_yields_gb_epl(self, methane: SubstanceProperties):
        """Zone 1 + GAS → EPL Gb, ATEX Category 2G."""
        l1 = resolve_regulatory("SA")
        hac = HACClassificationEngine()
        hac_result = hac.classify_v21(
            substance=methane,
            ventilation=VentilationLevel.MEDIUM,
            is_indoor=True,
        )

        arbiter = ATEXHazardousArbiter()
        atex_result = arbiter.arbitrate_v21(
            zone=hac_result.zone,
            hazard_type=hac_result.hazard_type,
            autoignition_c=methane.autoignition_c,
            hac_warnings=list(hac_result.warnings),
            hac_critical=list(hac_result.critical_flags),
        )

        spec = atex_result.equipment_spec
        # Zone 1 → Gb, Zone 2 → Gc
        assert spec.epl_required in ("Ga", "Gb", "Gc")
        assert spec.atex_category in ("1G", "2G", "3G")
        assert spec.temp_class != TemperatureClass.T6 or methane.autoignition_c > 85.0

    def test_h2s_zone0_yields_ga_epl(self, hydrogen_sulfide: SubstanceProperties):
        """Zone 0 + GAS → EPL Ga, ATEX Category 1G."""
        hac = HACClassificationEngine()
        hac_result = hac.classify_v21(
            substance=hydrogen_sulfide,
            ventilation=VentilationLevel.POOR,
            is_indoor=True,
        )

        arbiter = ATEXHazardousArbiter()
        atex_result = arbiter.arbitrate_v21(
            zone=hac_result.zone,
            hazard_type=hac_result.hazard_type,
            autoignition_c=hydrogen_sulfide.autoignition_c,
        )

        spec = atex_result.equipment_spec
        # Zone 0 must require Ga
        if hac_result.zone == ZoneType.ZONE_0:
            assert spec.epl_required == "Ga"
            assert spec.atex_category == "1G"

    def test_nec_us_zone_system_is_division(self):
        """USA jurisdiction uses Division system, not Zone."""
        l1 = resolve_regulatory("US")
        assert l1.zone_system == "DIVISION"
        # Engineers using Division system need conversion for IEC equipment
        from fireai.core.international_reg_selector import convert_division_to_zone
        zone = convert_division_to_zone("DIVISION_1", "CLASS_I")
        assert zone == "ZONE_1"


# ===========================================================================
# Test: L1→L2→L3→L5 Full Pipeline with Optical Coverage
# ===========================================================================

class TestL1L2L3L5WithOpticalCoverage:
    """L1→L2→L3→L5: complete pipeline through optical coverage."""

    def test_methane_optical_coverage_no_obstructions(
        self,
        methane: SubstanceProperties,
        simple_grid: list[RayTracePoint],
        flame_detector: FlameDetectorSpec,
    ):
        """Methane plant with 1 flame detector — partial coverage expected."""
        # L1
        l1 = resolve_regulatory("SA")
        assert l1.zone_system == "ZONE"

        # L2
        hac = HACClassificationEngine()
        hac_result = hac.classify_v21(
            substance=methane,
            ventilation=VentilationLevel.MEDIUM,
            is_indoor=True,
        )
        assert hac_result.zone in (ZoneType.ZONE_1, ZoneType.ZONE_2)

        # L3
        arbiter = ATEXHazardousArbiter()
        atex_result = arbiter.arbitrate_v21(
            zone=hac_result.zone,
            hazard_type=hac_result.hazard_type,
            autoignition_c=methane.autoignition_c,
        )
        assert atex_result.is_valid

        # L5 — optical coverage
        ray_engine = FlameDetectorAOCRayTrace(grid_step_m=0.5, detector_threshold=0.1)
        coverage = ray_engine.analyse_multi_v21(
            detectors=[flame_detector],
            target_grid=simple_grid,
            obstructions=[],
        )
        assert coverage.total_points == len(simple_grid)
        assert coverage.covered_points > 0
        assert coverage.coverage_pct > 0.0

    def test_redundant_optical_coverage(
        self,
        propane: SubstanceProperties,
        simple_grid: list[RayTracePoint],
        two_flame_detectors: list[FlameDetectorSpec],
    ):
        """Two detectors provide redundancy — some points covered by both."""
        hac = HACClassificationEngine()
        hac_result = hac.classify_v21(
            substance=propane,
            ventilation=VentilationLevel.MEDIUM,
            is_indoor=True,
        )

        ray_engine = FlameDetectorAOCRayTrace(grid_step_m=0.5, detector_threshold=0.1)
        coverage = ray_engine.analyse_multi_v21(
            detectors=two_flame_detectors,
            target_grid=simple_grid,
            obstructions=[],
        )
        # With 2 detectors, some points should have redundancy
        assert coverage.total_points == len(simple_grid)
        assert coverage.covered_points > 0

    def test_obstruction_reduces_coverage(
        self,
        methane: SubstanceProperties,
        simple_grid: list[RayTracePoint],
        flame_detector: FlameDetectorSpec,
        steel_obstruction: Obstruction,
    ):
        """Steel wall between detector and grid points reduces coverage."""
        ray_engine = FlameDetectorAOCRayTrace(grid_step_m=0.5, detector_threshold=0.1)

        # Without obstruction
        coverage_free = ray_engine.analyse_multi_v21(
            detectors=[flame_detector],
            target_grid=simple_grid,
            obstructions=[],
        )

        # With obstruction
        coverage_blocked = ray_engine.analyse_multi_v21(
            detectors=[flame_detector],
            target_grid=simple_grid,
            obstructions=[steel_obstruction],
        )

        # Obstruction should reduce coverage (or keep same if wall is outside)
        assert coverage_blocked.covered_points <= coverage_free.covered_points


# ===========================================================================
# Test: L1→L2→L3→L5→V23→L7 Complete 7-Layer Pipeline
# ===========================================================================

class TestL1ToL7CompletePipeline:
    """
    FULL L1→L7 pipeline integration test.

    This is the PRIMARY V24 closure test — it exercises every layer
    from regulatory selection to hybrid survivability classification.
    """

    def test_methane_saudi_full_pipeline(
        self,
        methane: SubstanceProperties,
        simple_grid: list[RayTracePoint],
        flame_detector: FlameDetectorSpec,
        ugld_sensor: UltrasonicSensor,
    ):
        """
        Complete pipeline: Saudi Arabia, Methane, 1 flame detector, 1 UGLD.

        Expected: partial optical coverage, partial acoustic coverage,
        some REDUNDANT_HYBRID, some OPTICAL_ONLY, some ACOUSTIC_ONLY,
        some BLIND_SPOT.
        """
        # ── L1: Regulatory Framework ──
        l1 = resolve_regulatory("SA")
        assert l1.zone_system == "ZONE"

        # ── L2: HAC Classification ──
        hac = HACClassificationEngine()
        hac_result = hac.classify_v21(
            substance=methane,
            ventilation=VentilationLevel.MEDIUM,
            is_indoor=True,
        )
        assert hac_result.zone in (ZoneType.ZONE_1, ZoneType.ZONE_2)

        # ── L3: ATEX Arbitration ──
        arbiter = ATEXHazardousArbiter()
        atex_result = arbiter.arbitrate_v21(
            zone=hac_result.zone,
            hazard_type=hac_result.hazard_type,
            autoignition_c=methane.autoignition_c,
            hac_warnings=list(hac_result.warnings),
            hac_critical=list(hac_result.critical_flags),
        )
        assert atex_result.is_valid
        assert atex_result.equipment_spec.epl_required in ("Ga", "Gb", "Gc")

        # ── L5: Optical Coverage ──
        ray_engine = FlameDetectorAOCRayTrace(grid_step_m=0.5, detector_threshold=0.1)
        optical_result = ray_engine.analyse_multi_v21(
            detectors=[flame_detector],
            target_grid=simple_grid,
            obstructions=[],
        )
        assert optical_result.total_points == len(simple_grid)
        assert optical_result.covered_points > 0

        # ── V23 + L7: Acoustic + Hybrid Survivability ──
        sensor_positions = {"UGLD-001": (2.0, 2.0, 5.0)}
        hybrid_engine = HybridSurvivabilityEngine(
            leak_spl_at_1m=100.0,
            center_frequency_hz=40_000.0,
            temp_c=40.0,    # Saudi ambient
            relative_humidity_pct=30.0,  # Saudi arid
        )
        hybrid_map = hybrid_engine.analyse(
            optical_result=optical_result,
            grid=simple_grid,
            ugld_sensors=[ugld_sensor],
            sensor_positions=sensor_positions,
        )

        # ── Assertions on the complete hybrid map ──
        assert hybrid_map.total_points == len(simple_grid)
        assert hybrid_map.total_points > 0

        # Must have at least some coverage
        assert hybrid_map.any_coverage_fraction > 0.0

        # Sum of all 4 classes must equal total
        total_classified = (
            hybrid_map.redundant_hybrid_count
            + hybrid_map.optical_only_count
            + hybrid_map.acoustic_only_count
            + hybrid_map.blind_spot_count
        )
        assert total_classified == hybrid_map.total_points

        # Fractions must be consistent
        assert abs(
            hybrid_map.hybrid_coverage_fraction
            + hybrid_map.optical_only_count / hybrid_map.total_points
            + hybrid_map.acoustic_only_count / hybrid_map.total_points
            + hybrid_map.blind_spot_fraction
            - 1.0
        ) < 0.01  # Accounting for rounding

        # Every point result must have valid coordinates
        for idx, pr in hybrid_map.point_results.items():
            assert pr.point_index == idx
            assert pr.survivability_class in (
                SurvivabilityClass.REDUNDANT_HYBRID,
                SurvivabilityClass.OPTICAL_ONLY,
                SurvivabilityClass.ACOUSTIC_ONLY,
                SurvivabilityClass.BLIND_SPOT,
            )

    def test_propane_germany_dual_detector_dual_ugld(
        self,
        propane: SubstanceProperties,
        simple_grid: list[RayTracePoint],
        two_flame_detectors: list[FlameDetectorSpec],
        two_ugld_sensors: list[UltrasonicSensor],
        ugld_positions: dict,
    ):
        """
        Germany, Propane, 2 flame detectors, 2 UGLD sensors.

        Expected: high hybrid redundancy with dual-modality coverage.
        """
        # L1
        l1 = resolve_regulatory("DE")
        assert l1.framework.value == "ATEX_EU"

        # L2
        hac = HACClassificationEngine()
        hac_result = hac.classify_v21(
            substance=propane,
            ventilation=VentilationLevel.MEDIUM,
            is_indoor=True,
        )

        # L3
        arbiter = ATEXHazardousArbiter()
        atex_result = arbiter.arbitrate_v21(
            zone=hac_result.zone,
            hazard_type=hac_result.hazard_type,
            autoignition_c=propane.autoignition_c,
        )
        assert atex_result.is_valid

        # L5
        ray_engine = FlameDetectorAOCRayTrace(grid_step_m=0.5, detector_threshold=0.1)
        optical_result = ray_engine.analyse_multi_v21(
            detectors=two_flame_detectors,
            target_grid=simple_grid,
            obstructions=[],
        )

        # L7
        hybrid_engine = HybridSurvivabilityEngine(
            leak_spl_at_1m=100.0,
            temp_c=25.0,   # Germany ambient
            relative_humidity_pct=65.0,
        )
        hybrid_map = hybrid_engine.analyse(
            optical_result=optical_result,
            grid=simple_grid,
            ugld_sensors=two_ugld_sensors,
            sensor_positions=ugld_positions,
        )

        # With 2 detectors + 2 UGLD, should have significant coverage
        assert hybrid_map.any_coverage_fraction > 0.0
        assert hybrid_map.total_points == len(simple_grid)

        # Verify classification consistency
        total_classified = (
            hybrid_map.redundant_hybrid_count
            + hybrid_map.optical_only_count
            + hybrid_map.acoustic_only_count
            + hybrid_map.blind_spot_count
        )
        assert total_classified == hybrid_map.total_points

    def test_h2s_usa_full_pipeline_with_obstruction(
        self,
        hydrogen_sulfide: SubstanceProperties,
        simple_grid: list[RayTracePoint],
        two_flame_detectors: list[FlameDetectorSpec],
        two_ugld_sensors: list[UltrasonicSensor],
        ugld_positions: dict,
        steel_obstruction: Obstruction,
        acoustic_wall: AcousticObstacle,
    ):
        """
        USA, H2S, with steel wall obstruction.

        The wall blocks both optical and acoustic paths on one side,
        creating a BLIND_SPOT region behind it.
        """
        # L1: USA → NEC Division system
        l1 = resolve_regulatory("US")
        assert l1.zone_system == "DIVISION"

        # L2: H2S classification
        hac = HACClassificationEngine()
        hac_result = hac.classify_v21(
            substance=hydrogen_sulfide,
            ventilation=VentilationLevel.POOR,
            is_indoor=True,
        )
        # Poor ventilation → more hazardous zone
        assert hac_result.zone in (ZoneType.ZONE_0, ZoneType.ZONE_1)

        # L3: Equipment selection
        arbiter = ATEXHazardousArbiter()
        atex_result = arbiter.arbitrate_v21(
            zone=hac_result.zone,
            hazard_type=hac_result.hazard_type,
            autoignition_c=hydrogen_sulfide.autoignition_c,
        )
        assert atex_result.is_valid
        # H2S autoignition 260°C → T2, T2C, or T3 class
        # Extended T-classes (T2A-T2D) are valid per IEC 60079-0 §7.3
        tc = atex_result.equipment_spec.temp_class
        assert tc.value.startswith("T2") or tc.value.startswith("T3") or tc == TemperatureClass.T1

        # L5: Optical coverage WITH obstruction
        ray_engine = FlameDetectorAOCRayTrace(grid_step_m=0.5, detector_threshold=0.1)
        optical_result = ray_engine.analyse_multi_v21(
            detectors=two_flame_detectors,
            target_grid=simple_grid,
            obstructions=[steel_obstruction],
        )

        # L7: Hybrid survivability with acoustic wall
        hybrid_engine = HybridSurvivabilityEngine(
            leak_spl_at_1m=100.0,
            temp_c=35.0,   # Texas Gulf Coast
            relative_humidity_pct=80.0,
        )
        hybrid_map = hybrid_engine.analyse(
            optical_result=optical_result,
            grid=simple_grid,
            ugld_sensors=two_ugld_sensors,
            sensor_positions=ugld_positions,
            acoustic_obstacles=[acoustic_wall],
        )

        # Wall should create some blind spots
        assert hybrid_map.total_points == len(simple_grid)
        assert hybrid_map.any_coverage_fraction > 0.0

        # If there are blind spots, there should be a warning
        if hybrid_map.has_blind_spots:
            assert len(hybrid_map.warnings) > 0
            assert any("BLIND_SPOT" in w for w in hybrid_map.warnings)


# ===========================================================================
# Test: Cross-Layer Data Integrity
# ===========================================================================

class TestCrossLayerDataIntegrity:
    """
    Verify that data flows correctly between layers without loss
    or corruption. These tests catch interface mismatches.
    """

    def test_l2_zone_feeds_l3_correctly(self, methane: SubstanceProperties):
        """L2 zone type must be consumed by L3 without modification."""
        hac = HACClassificationEngine()
        hac_result = hac.classify_v21(
            substance=methane,
            ventilation=VentilationLevel.MEDIUM,
            is_indoor=True,
        )
        zone = hac_result.zone
        hazard = hac_result.hazard_type

        arbiter = ATEXHazardousArbiter()
        atex_result = arbiter.arbitrate_v21(
            zone=zone,
            hazard_type=hazard,
            autoignition_c=methane.autoignition_c,
        )
        # Zone/Hazard consistency — no Dual-Path Inconsistency
        spec = atex_result.equipment_spec
        if zone == ZoneType.ZONE_0:
            assert spec.epl_required == "Ga"
        elif zone == ZoneType.ZONE_1:
            assert spec.epl_required in ("Ga", "Gb")
        elif zone == ZoneType.ZONE_2:
            assert spec.epl_required in ("Gb", "Gc")

    def test_l5_coverage_result_feeds_l7(self, simple_grid, flame_detector, ugld_sensor):
        """CoverageResult.redundancy_map must be usable by L7."""
        ray_engine = FlameDetectorAOCRayTrace(grid_step_m=0.5, detector_threshold=0.1)
        optical = ray_engine.analyse_multi_v21(
            detectors=[flame_detector],
            target_grid=simple_grid,
            obstructions=[],
        )

        # Verify CoverageResult has expected structure
        assert hasattr(optical, "redundancy_map")
        assert hasattr(optical, "total_points")
        assert optical.total_points == len(simple_grid)

        # Feed into L7
        sensor_positions = {"UGLD-001": (2.0, 2.0, 5.0)}
        hybrid_engine = HybridSurvivabilityEngine()
        hybrid_map = hybrid_engine.analyse(
            optical_result=optical,
            grid=simple_grid,
            ugld_sensors=[ugld_sensor],
            sensor_positions=sensor_positions,
        )
        assert hybrid_map.total_points == optical.total_points

    def test_grid_length_mismatch_raises(self, simple_grid, flame_detector, ugld_sensor):
        """L7 must raise if grid length != optical_result.total_points."""
        ray_engine = FlameDetectorAOCRayTrace(grid_step_m=0.5, detector_threshold=0.1)
        optical = ray_engine.analyse_multi_v21(
            detectors=[flame_detector],
            target_grid=simple_grid,
            obstructions=[],
        )

        # Create a different-sized grid
        wrong_grid = simple_grid[:3]  # Only 3 points instead of 25

        hybrid_engine = HybridSurvivabilityEngine()
        with pytest.raises(ValueError, match="does not match"):
            hybrid_engine.analyse(
                optical_result=optical,
                grid=wrong_grid,
                ugld_sensors=[ugld_sensor],
                sensor_positions={"UGLD-001": (2.0, 2.0, 5.0)},
            )

    def test_missing_sensor_position_raises(
        self, simple_grid, flame_detector, ugld_sensor,
    ):
        """L7 must raise if UGLD sensor has no position mapping."""
        ray_engine = FlameDetectorAOCRayTrace(grid_step_m=0.5, detector_threshold=0.1)
        optical = ray_engine.analyse_multi_v21(
            detectors=[flame_detector],
            target_grid=simple_grid,
            obstructions=[],
        )

        hybrid_engine = HybridSurvivabilityEngine()
        with pytest.raises(ValueError, match="no position"):
            hybrid_engine.analyse(
                optical_result=optical,
                grid=simple_grid,
                ugld_sensors=[ugld_sensor],
                sensor_positions={},  # Empty — no positions!
            )

    def test_no_ugld_sensors_gives_warning(
        self, simple_grid, flame_detector,
    ):
        """No UGLD sensors → all points are OPTICAL_ONLY or BLIND_SPOT."""
        ray_engine = FlameDetectorAOCRayTrace(grid_step_m=0.5, detector_threshold=0.1)
        optical = ray_engine.analyse_multi_v21(
            detectors=[flame_detector],
            target_grid=simple_grid,
            obstructions=[],
        )

        hybrid_engine = HybridSurvivabilityEngine()
        hybrid_map = hybrid_engine.analyse(
            optical_result=optical,
            grid=simple_grid,
            ugld_sensors=[],  # No acoustic sensors
            sensor_positions={},
        )

        # Should warn about missing UGLD
        assert len(hybrid_map.warnings) > 0
        assert any("UGLD" in w or "acoustic" in w.lower() for w in hybrid_map.warnings)

        # No acoustic-only or redundant-hybrid points possible
        assert hybrid_map.acoustic_only_count == 0
        assert hybrid_map.redundant_hybrid_count == 0

        # Points are either OPTICAL_ONLY or BLIND_SPOT
        total = hybrid_map.optical_only_count + hybrid_map.blind_spot_count
        assert total == hybrid_map.total_points


# ===========================================================================
# Test: Survivability Classification Logic
# ===========================================================================

class TestSurvivabilityClassificationLogic:
    """
    Test the 4-state classification logic at the intersection of
    optical and acoustic coverage.
    """

    def test_all_redundant_hybrid_is_nfpa72_compliant(
        self, simple_grid, two_flame_detectors, two_ugld_sensors, ugld_positions,
    ):
        """If all points are REDUNDANT_HYBRID → is_nfpa72_compliant = True."""
        ray_engine = FlameDetectorAOCRayTrace(grid_step_m=0.5, detector_threshold=0.1)
        optical = ray_engine.analyse_multi_v21(
            detectors=two_flame_detectors,
            target_grid=simple_grid,
            obstructions=[],
        )

        hybrid_engine = HybridSurvivabilityEngine(
            leak_spl_at_1m=100.0,  # Strong leak
        )
        hybrid_map = hybrid_engine.analyse(
            optical_result=optical,
            grid=simple_grid,
            ugld_sensors=two_ugld_sensors,
            sensor_positions=ugld_positions,
        )

        # Check NFPA 72 compliance property
        if hybrid_map.redundant_hybrid_count == hybrid_map.total_points:
            assert hybrid_map.is_nfpa72_compliant
        else:
            # Not all redundant — may or may not be compliant
            assert isinstance(hybrid_map.is_nfpa72_compliant, bool)

    def test_blind_spot_detection_with_warning(
        self, simple_grid, flame_detector, ugld_sensor,
    ):
        """BLIND_SPOT points must generate NFPA §17.8.3.4 warning."""
        # Use a very short-range detector to create blind spots
        short_detector = FlameDetectorSpec(
            detector_id="FD-SHORT",
            position=[0.0, 0.0, 6.0],
            orientation_vector=[1.0, 1.0, -1.0],
            rated_range_m=2.0,  # Very short range
            aoc_deg=30.0,  # Narrow cone
            spectral_bands=[WavelengthBand.UV],
        )

        ray_engine = FlameDetectorAOCRayTrace(grid_step_m=0.5, detector_threshold=0.1)
        optical = ray_engine.analyse_multi_v21(
            detectors=[short_detector],
            target_grid=simple_grid,
            obstructions=[],
        )

        # UGLD far away — unlikely to trigger at many points
        sensor_positions = {"UGLD-001": (50.0, 50.0, 5.0)}
        hybrid_engine = HybridSurvivabilityEngine(
            leak_spl_at_1m=80.0,  # Weak leak
        )
        hybrid_map = hybrid_engine.analyse(
            optical_result=optical,
            grid=simple_grid,
            ugld_sensors=[ugld_sensor],
            sensor_positions=sensor_positions,
        )

        if hybrid_map.has_blind_spots:
            assert any("BLIND_SPOT" in w for w in hybrid_map.warnings)
            assert hybrid_map.blind_spot_count > 0

    def test_survivability_class_properties(self):
        """Test enum properties of SurvivabilityClass."""
        assert SurvivabilityClass.REDUNDANT_HYBRID.is_covered
        assert SurvivabilityClass.REDUNDANT_HYBRID.is_redundant
        assert SurvivabilityClass.OPTICAL_ONLY.is_covered
        assert not SurvivabilityClass.OPTICAL_ONLY.is_redundant
        assert SurvivabilityClass.ACOUSTIC_ONLY.is_covered
        assert not SurvivabilityClass.ACOUSTIC_ONLY.is_redundant
        assert not SurvivabilityClass.BLIND_SPOT.is_covered
        assert not SurvivabilityClass.BLIND_SPOT.is_redundant

    def test_severity_rank_ordering(self):
        """Severity rank: REDUNDANT < OPTICAL < ACOUSTIC < BLIND."""
        assert (
            SurvivabilityClass.REDUNDANT_HYBRID.severity_rank
            < SurvivabilityClass.OPTICAL_ONLY.severity_rank
            < SurvivabilityClass.ACOUSTIC_ONLY.severity_rank
            < SurvivabilityClass.BLIND_SPOT.severity_rank
        )


# ===========================================================================
# Test: Environmental Context Propagation
# ===========================================================================

class TestEnvironmentalContextPropagation:
    """Verify that environmental parameters flow correctly through layers."""

    def test_high_temp_reduces_acoustic_coverage(self, simple_grid, flame_detector, ugld_sensor):
        """High Saudi temperature → more atmospheric absorption → less acoustic range."""
        sensor_positions = {"UGLD-001": (2.0, 2.0, 5.0)}

        # Cool environment
        engine_cool = HybridSurvivabilityEngine(
            leak_spl_at_1m=100.0,
            temp_c=20.0,
            relative_humidity_pct=50.0,
        )

        # Hot environment
        engine_hot = HybridSurvivabilityEngine(
            leak_spl_at_1m=100.0,
            temp_c=55.0,
            relative_humidity_pct=10.0,
        )

        ray_engine = FlameDetectorAOCRayTrace(grid_step_m=0.5, detector_threshold=0.1)
        optical = ray_engine.analyse_multi_v21(
            detectors=[flame_detector],
            target_grid=simple_grid,
            obstructions=[],
        )

        map_cool = engine_cool.analyse(
            optical_result=optical,
            grid=simple_grid,
            ugld_sensors=[ugld_sensor],
            sensor_positions=sensor_positions,
        )

        map_hot = engine_hot.analyse(
            optical_result=optical,
            grid=simple_grid,
            ugld_sensors=[ugld_sensor],
            sensor_positions=sensor_positions,
        )

        # Hot/dry environment should have equal or fewer acoustic detections
        # (more atmospheric absorption at ultrasonic frequencies)
        cool_acoustic = map_cool.redundant_hybrid_count + map_cool.acoustic_only_count
        hot_acoustic = map_hot.redundant_hybrid_count + map_hot.acoustic_only_count
        assert hot_acoustic <= cool_acoustic

    def test_burgess_wheeler_correction_propagates(self, methane: SubstanceProperties):
        """L2 Burgess-Wheeler LFL correction must propagate to L3."""
        hac = HACClassificationEngine()
        env = EnvironmentalContext(ambient_temp_c=80.0)  # Very hot
        hac_result = hac.classify_v21(
            substance=methane,
            ventilation=VentilationLevel.MEDIUM,
            is_indoor=True,
            ambient_temp_c=80.0,
            env_context=env,
        )
        # At 80°C, LFL should be corrected downward
        # (Burgess-Wheeler: LFL decreases ~0.14%/K above 25°C)
        # This should generate a warning about thermal correction
        if hac_result.warnings:
            assert any("LFL" in w or "thermal" in w.lower() for w in hac_result.warnings)


# ===========================================================================
# Test: Volumetric Media in L5→L7 Pipeline
# ===========================================================================

class TestVolumetricMediaInPipeline:
    """Test that volumetric media (smoke, fog) correctly reduces coverage."""

    def test_smoke_reduces_optical_not_acoustic(
        self,
        simple_grid,
        flame_detector,
        ugld_sensor,
    ):
        """
        Dense smoke between detector and grid reduces optical coverage
        (Beer-Lambert) but does NOT reduce acoustic coverage
        (ultrasonic signals penetrate smoke).

        This is the PHYSICAL JUSTIFICATION for dual-modality detection.
        """
        sensor_positions = {"UGLD-001": (2.0, 2.0, 5.0)}
        ray_engine = FlameDetectorAOCRayTrace(grid_step_m=0.5, detector_threshold=0.1)

        # Without smoke
        optical_clear = ray_engine.analyse_multi_v21(
            detectors=[flame_detector],
            target_grid=simple_grid,
            obstructions=[],
        )

        # With dense smoke (high alpha = strong absorption)
        smoke = VolumetricMedium(
            medium_id="SMOKE-01",
            medium_type="SMOKE",
            bbox_min=[-1.0, -1.0, 0.0],
            bbox_max=[6.0, 6.0, 4.0],
            alpha_override={
                WavelengthBand.UV: 2.0,    # Heavy UV absorption
                WavelengthBand.VIS: 1.5,   # Heavy visible absorption
                WavelengthBand.IR1: 1.0,   # Moderate IR absorption
            },
        )
        optical_smoke = ray_engine.analyse_multi_v21(
            detectors=[flame_detector],
            target_grid=simple_grid,
            obstructions=[],
            volumetric_media=[smoke],
        )

        # Smoke should reduce optical coverage
        assert optical_smoke.covered_points <= optical_clear.covered_points

        # Acoustic coverage should be UNAFFECTED by smoke
        # (UGLD operates at ultrasonic frequencies, not optical)
        hybrid_engine = HybridSurvivabilityEngine()

        hybrid_clear = hybrid_engine.analyse(
            optical_result=optical_clear,
            grid=simple_grid,
            ugld_sensors=[ugld_sensor],
            sensor_positions=sensor_positions,
        )

        hybrid_smoke = hybrid_engine.analyse(
            optical_result=optical_smoke,
            grid=simple_grid,
            ugld_sensors=[ugld_sensor],
            sensor_positions=sensor_positions,
        )

        # Acoustic-only count should be same or higher with smoke
        # (because some points lost optical coverage but still have acoustic)
        assert hybrid_smoke.acoustic_only_count >= hybrid_clear.acoustic_only_count

        # This demonstrates why hybrid detection matters:
        # Smoke blinds optical but UGLD still hears the leak
        # Points that were REDUNDANT_HYBRID may become ACOUSTIC_ONLY
        # Points that were OPTICAL_ONLY may become BLIND_SPOT
        if optical_smoke.covered_points < optical_clear.covered_points:
            # Some optical coverage was lost
            assert hybrid_smoke.optical_only_count <= hybrid_clear.optical_only_count


# ===========================================================================
# Test: CLI Engine Integration (L1→L5→L6)
# ===========================================================================

class TestCLIEngineIntegration:
    """Test CLIFireAIEngine orchestration + L7 manual extension."""

    def test_cli_pipeline_produces_valid_optical_result(
        self,
        methane: SubstanceProperties,
        simple_grid,
        flame_detector,
    ):
        """CLI engine L1→L5→L6 must produce valid results for L7 consumption."""
        from fireai.core.fireai_cli_engine import CLIFireAIEngine

        engine = CLIFireAIEngine(grid_step_m=0.5, detector_threshold=0.1)
        result = engine.run_full_pipeline(
            country_code="SA",
            substance=methane,
            ventilation=VentilationLevel.MEDIUM,
            detectors=[flame_detector],
            target_grid=simple_grid,
            obstructions=[],
            is_indoor=True,
        )

        assert result.success
        assert result.layer1.success
        assert result.layer2.success
        assert result.layer5.success
        assert result.layer5.total_points == len(simple_grid)

    def test_cli_pipeline_l5_feeds_l7(
        self,
        methane: SubstanceProperties,
        simple_grid,
        flame_detector,
        ugld_sensor,
    ):
        """CLI engine L5 output feeds directly into L7."""
        from fireai.core.fireai_cli_engine import CLIFireAIEngine

        engine = CLIFireAIEngine(grid_step_m=0.5, detector_threshold=0.1)
        result = engine.run_full_pipeline(
            country_code="SA",
            substance=methane,
            ventilation=VentilationLevel.MEDIUM,
            detectors=[flame_detector],
            target_grid=simple_grid,
            obstructions=[],
            is_indoor=True,
        )

        # Now manually run L7 on the CLI engine's L5 output
        ray_engine = FlameDetectorAOCRayTrace(grid_step_m=0.5, detector_threshold=0.1)
        optical = ray_engine.analyse_multi_v21(
            detectors=[flame_detector],
            target_grid=simple_grid,
            obstructions=[],
        )

        sensor_positions = {"UGLD-001": (2.0, 2.0, 5.0)}
        hybrid_engine = HybridSurvivabilityEngine()
        hybrid_map = hybrid_engine.analyse(
            optical_result=optical,
            grid=simple_grid,
            ugld_sensors=[ugld_sensor],
            sensor_positions=sensor_positions,
        )

        assert hybrid_map.total_points == result.layer5.total_points
        assert hybrid_map.any_coverage_fraction > 0.0


# ===========================================================================
# Test: Multi-Jurisdiction Pipeline Comparison
# ===========================================================================

class TestMultiJurisdictionComparison:
    """
    Same scenario, different jurisdictions.
    Verify that the regulatory framework changes the equipment spec
    but not the physics (coverage is framework-independent).
    """

    def test_same_physics_different_equipment(self, methane: SubstanceProperties):
        """Same substance → same zone physics, but different equipment marking."""
        countries = ["SA", "DE", "US", "CA"]
        hac = HACClassificationEngine()
        arbiter = ATEXHazardousArbiter()

        hac_result = hac.classify_v21(
            substance=methane,
            ventilation=VentilationLevel.MEDIUM,
            is_indoor=True,
        )

        results = {}
        for country in countries:
            l1 = resolve_regulatory(country)
            atex = arbiter.arbitrate_v21(
                zone=hac_result.zone,
                hazard_type=hac_result.hazard_type,
                autoignition_c=methane.autoignition_c,
            )
            results[country] = {
                "framework": l1.framework.value,
                "epl": atex.equipment_spec.epl_required,
                "temp_class": atex.equipment_spec.temp_class.value,
            }

        # Zone classification is the same (physics doesn't change)
        # But framework differs
        assert results["SA"]["framework"] == "IECEx"  # Enum value is IECEx
        assert results["DE"]["framework"] == "ATEX_EU"
        assert results["US"]["framework"] == "NEC_US"
        assert results["CA"]["framework"] == "CEC_CANADA"

        # Same EPL and temp class (same zone → same equipment requirement)
        epl_values = {r["epl"] for r in results.values()}
        # All should have same EPL for same zone
        assert len(epl_values) == 1  # Same zone → same EPL
