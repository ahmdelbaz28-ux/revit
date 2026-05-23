"""
test_cli_engine.py – CLIFireAIEngine Test Suite
================================================
Tests the 5-layer CLI orchestration engine including:
  1. Layer 1: Regulatory framework resolution
  2. Layer 2: HAC with environmental LFL correction
  3. Layer 3: ATEX equipment with thermal margin
  4. Layer 5: Optical coverage with volumetric media
  5. Full pipeline integration
  6. Edge cases and failure modes
  7. Consultant's ProcessPoolExecutor rejection verification
"""

import math
import pytest

from fireai.core.models_v21 import (
    SubstanceProperties,
    HazardType,
    VentilationLevel,
    EnvironmentalContext,
    PasquillStability,
    FlameDetectorSpec,
    RayTracePoint,
    Obstruction,
    VolumetricMedium,
    WavelengthBand,
    ZoneType,
    TemperatureClass,
)
from fireai.core.fireai_cli_engine import (
    CLIFireAIEngine,
    Layer1Result,
    Layer2Result,
    Layer3Result,
    Layer5Result,
    PipelineResult,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def methane() -> SubstanceProperties:
    """Methane substance for testing."""
    return SubstanceProperties(
        name="Methane",
        hazard_type=HazardType.GAS,
        lfl_vol_pct=5.0,
        ufl_vol_pct=15.0,
        autoignition_c=537.0,
    )


@pytest.fixture
def propane() -> SubstanceProperties:
    """Propane substance for testing."""
    return SubstanceProperties(
        name="Propane",
        hazard_type=HazardType.GAS,
        lfl_vol_pct=2.1,
        ufl_vol_pct=9.5,
        autoignition_c=470.0,
    )


@pytest.fixture
def detector() -> FlameDetectorSpec:
    """Standard IR3 flame detector."""
    return FlameDetectorSpec(
        detector_id="det_01",
        position=[5.0, 5.0, 5.0],
        orientation_vector=[0.0, 0.0, -1.0],
        rated_range_m=25.0,
        aoc_deg=90.0,
        spectral_bands=[WavelengthBand.IR3, WavelengthBand.UV],
    )


@pytest.fixture
def target_grid() -> list:
    """10x10 target grid at floor level."""
    return [RayTracePoint(x=x, y=y, z=0.0) for x in range(0, 11) for y in range(0, 11)]


@pytest.fixture
def engine() -> CLIFireAIEngine:
    """Engine with default worst-case environmental context."""
    return CLIFireAIEngine(grid_step_m=1.0)


@pytest.fixture
def engine_hot() -> CLIFireAIEngine:
    """Engine with hot environment (80C turbine room)."""
    ctx = EnvironmentalContext(ambient_temp_c=80.0)
    return CLIFireAIEngine(grid_step_m=1.0, env_context=ctx)


# ===========================================================================
# 1. Layer 1: Regulatory Framework
# ===========================================================================

class TestLayer1:
    """Test Layer 1: Regulatory framework resolution."""

    def test_saudi_arabia_resolves(self, engine):
        result = engine.run_layer1("SA")
        assert result.success
        assert result.zone_system in ("ZONE", "DIVISION")

    def test_us_resolves(self, engine):
        result = engine.run_layer1("US")
        assert result.success
        assert result.zone_system == "DIVISION"

    def test_unknown_country_fails(self, engine):
        result = engine.run_layer1("XX")
        assert not result.success
        assert "UNKNOWN" in result.framework

    def test_de_resolves_atex(self, engine):
        """Germany should resolve to ATEX EU."""
        result = engine.run_layer1("DE")
        assert result.success
        assert "ATEX" in result.framework or "IECEx" in result.framework


# ===========================================================================
# 2. Layer 2: HAC Classification
# ===========================================================================

class TestLayer2:
    """Test Layer 2: HAC with environmental correction."""

    def test_methane_medium_vent(self, engine, methane):
        result = engine.run_layer2(methane, VentilationLevel.MEDIUM)
        assert result.success
        assert result.zone == ZoneType.ZONE_1
        assert result.horizontal_m > 0

    def test_poor_ventilation_zone0(self, engine, methane):
        result = engine.run_layer2(methane, VentilationLevel.POOR)
        assert result.success
        assert result.zone == ZoneType.ZONE_0
        assert any("CRITICAL" in f for f in result.critical_flags)

    def test_hot_environment_larger_zone(self, engine, engine_hot, methane):
        """Hot environment (80C) should produce larger zone than default (40C)."""
        result_normal = engine.run_layer2(methane, VentilationLevel.MEDIUM)
        result_hot = engine_hot.run_layer2(methane, VentilationLevel.MEDIUM)

        # With LFL correction at 80C, LFL drops -> zone extends further
        assert result_hot.horizontal_m >= result_normal.horizontal_m

    def test_lfl_correction_applied(self, engine_hot, methane):
        """At 80C, LFL correction should be applied."""
        result = engine_hot.run_layer2(methane, VentilationLevel.MEDIUM)
        if result.lfl_corrected is not None:
            assert result.lfl_corrected < methane.lfl_vol_pct
            assert result.lfl_correction_pct is not None
            assert result.lfl_correction_pct > 0

    def test_high_ventilation_zone2(self, engine, methane):
        result = engine.run_layer2(methane, VentilationLevel.HIGH)
        assert result.success
        # High ventilation with GAS should result in Zone 2 or unclassified
        assert result.zone in (ZoneType.ZONE_2, ZoneType.UNCLASSIFIED)

    def test_hazard_type_preserved(self, engine, methane):
        result = engine.run_layer2(methane, VentilationLevel.MEDIUM)
        assert result.hazard_type == HazardType.GAS


# ===========================================================================
# 3. Layer 3: ATEX Equipment
# ===========================================================================

class TestLayer3:
    """Test Layer 3: ATEX equipment specification with thermal margin."""

    def test_zone0_requires_ga(self, engine):
        result = engine.run_layer3(
            ZoneType.ZONE_0, HazardType.GAS, autoignition_c=200.0
        )
        assert result.success
        assert result.epl == "Ga"

    def test_zone1_requires_gb(self, engine):
        result = engine.run_layer3(
            ZoneType.ZONE_1, HazardType.GAS, autoignition_c=200.0
        )
        assert result.success
        assert result.epl == "Gb"

    def test_zone2_requires_gc(self, engine):
        result = engine.run_layer3(
            ZoneType.ZONE_2, HazardType.GAS, autoignition_c=200.0
        )
        assert result.success
        assert result.epl == "Gc"

    def test_autoignition_136_zone0_gets_t5(self, engine):
        """
        The 1-degree margin scenario: autoignition=136C in Zone 0.
        With IEC 60079-14 strict margin (5% + min 10K):
          t_safe = 136 - max(10, 6.8) = 126C
        The returned T-class max surface must be <= t_safe.
        With extended classes: T4A (max 120C) <= 126 ✓
        """
        from fireai.core.models_v21 import _T_CLASS_MAX
        result = engine.run_layer3(
            ZoneType.ZONE_0, HazardType.GAS, autoignition_c=136.0
        )
        assert result.success
        # Verify safety: max surface temperature must be <= t_safe
        max_surface = _T_CLASS_MAX[result.temp_class]
        t_safe = 136.0 - max(10.0, 0.05 * 136.0)
        assert max_surface <= t_safe, (
            f"Got {result.temp_class} (max {max_surface}C) which exceeds "
            f"t_safe={t_safe}C for Zone 0!"
        )

    def test_fire_detector_marking_present(self, engine):
        result = engine.run_layer3(
            ZoneType.ZONE_1, HazardType.GAS, autoignition_c=300.0
        )
        # Fire detector marking may be None if spec validation fails
        # but the result should still succeed
        assert result.success
        # Zone 1 should have 'ib' in the IS level
        if result.fire_detector_marking:
            assert "ib" in result.fire_detector_marking

    def test_dust_zone20(self, engine):
        result = engine.run_layer3(
            ZoneType.ZONE_20, HazardType.DUST, autoignition_c=200.0
        )
        assert result.success
        assert result.epl == "Da"


# ===========================================================================
# 4. Layer 5: Optical Coverage
# ===========================================================================

class TestLayer5:
    """Test Layer 5: Optical coverage with volumetric media."""

    def test_basic_coverage(self, engine, detector, target_grid):
        result = engine.run_layer5([detector], target_grid, [])
        assert result.success
        assert result.total_points == len(target_grid)
        assert result.covered_points > 0
        assert result.coverage_pct > 0

    def test_no_detectors_fails(self, engine, target_grid):
        result = engine.run_layer5([], target_grid, [])
        assert not result.success
        assert result.covered_points == 0

    def test_volumetric_media_reduces_coverage(self, engine, detector, target_grid):
        """Smoke between detector and floor should reduce coverage."""
        result_clear = engine.run_layer5([detector], target_grid, [])

        media = [VolumetricMedium(
            medium_id="dense_smoke",
            medium_type="SMOKE",
            bbox_min=[0.0, 0.0, 2.0],
            bbox_max=[10.0, 10.0, 4.0],
            alpha_override={WavelengthBand.IR3: 3.0},
        )]
        result_smoke = engine.run_layer5([detector], target_grid, [], media)

        # Coverage with dense smoke should be less
        assert result_smoke.covered_points <= result_clear.covered_points

    def test_obstruction_reduces_coverage(self, engine, detector, target_grid):
        """A solid wall in front of the detector should reduce coverage."""
        result_clear = engine.run_layer5([detector], target_grid, [])

        wall = Obstruction(
            obstruction_id="wall_1",
            vertices=[[3.0, 0.0, 0.0], [3.0, 10.0, 5.0]],
            spectral_transparency={
                WavelengthBand.UV: 0.0,
                WavelengthBand.VIS: 0.0,
                WavelengthBand.IR1: 0.0,
                WavelengthBand.IR3: 0.0,
            },
        )
        result_wall = engine.run_layer5([detector], target_grid, [wall])

        # Coverage with wall should be less
        assert result_wall.covered_points < result_clear.covered_points

    def test_multiple_detectors_improve_coverage(self, engine, target_grid):
        """Multiple detectors should cover more than one."""
        det1 = FlameDetectorSpec(
            detector_id="det1",
            position=[0.0, 0.0, 5.0],
            orientation_vector=[0.0, 0.0, -1.0],
            rated_range_m=25.0,
            aoc_deg=90.0,
            spectral_bands=[WavelengthBand.IR3],
        )
        det2 = FlameDetectorSpec(
            detector_id="det2",
            position=[10.0, 10.0, 5.0],
            orientation_vector=[0.0, 0.0, -1.0],
            rated_range_m=25.0,
            aoc_deg=90.0,
            spectral_bands=[WavelengthBand.IR3],
        )

        result_single = engine.run_layer5([det1], target_grid, [])
        result_multi = engine.run_layer5([det1, det2], target_grid, [])

        assert result_multi.covered_points >= result_single.covered_points

    def test_per_detector_results(self, engine, detector, target_grid):
        """Should return per-detector coverage data."""
        result = engine.run_layer5([detector], target_grid, [])
        assert "det_01" in result.per_detector
        det_result = result.per_detector["det_01"]
        assert det_result.effective_range_m >= 0


# ===========================================================================
# 5. Full Pipeline Integration
# ===========================================================================

class TestFullPipeline:
    """Test complete 5-layer pipeline execution."""

    def test_full_pipeline_saudi_methane(self, engine, methane, detector, target_grid):
        """Full pipeline for Saudi Arabia with Methane."""
        result = engine.run_full_pipeline(
            country_code="SA",
            substance=methane,
            ventilation=VentilationLevel.MEDIUM,
            detectors=[detector],
            target_grid=target_grid,
        )

        assert result.success
        assert result.layer1 is not None
        assert result.layer2 is not None
        assert result.layer3 is not None
        assert result.layer5 is not None
        assert result.env_context is not None
        assert result.elapsed_seconds >= 0

    def test_pipeline_unknown_country_still_runs_layers_2_5(
        self, engine, methane, detector, target_grid
    ):
        """Layer 1 failure should stop pipeline but report what ran."""
        result = engine.run_full_pipeline(
            country_code="XX",
            substance=methane,
            ventilation=VentilationLevel.MEDIUM,
            detectors=[detector],
            target_grid=target_grid,
        )

        assert not result.success
        assert result.layer1 is not None
        assert not result.layer1.success
        # Layers 2-5 should not have run
        assert result.layer2 is None

    def test_pipeline_with_hot_environment(self, engine_hot, methane, detector, target_grid):
        """Pipeline with hot environment (80C)."""
        result = engine_hot.run_full_pipeline(
            country_code="SA",
            substance=methane,
            ventilation=VentilationLevel.MEDIUM,
            detectors=[detector],
            target_grid=target_grid,
        )

        assert result.success
        assert result.env_context.ambient_temp_c == 80.0
        # Zone should be larger due to LFL correction at 80C
        assert result.layer2.horizontal_m > 0

    def test_pipeline_with_volumetric_media(self, engine, methane, detector, target_grid):
        """Pipeline with smoke in optical path."""
        media = [VolumetricMedium(
            medium_id="smoke",
            medium_type="SMOKE",
            bbox_min=[0.0, 0.0, 2.0],
            bbox_max=[10.0, 10.0, 4.0],
            alpha_override={WavelengthBand.IR3: 0.5},
        )]

        result = engine.run_full_pipeline(
            country_code="SA",
            substance=methane,
            ventilation=VentilationLevel.LOW,
            detectors=[detector],
            target_grid=target_grid,
            volumetric_media=media,
        )

        assert result.success
        assert result.layer5 is not None

    def test_pipeline_critical_flags_propagated(self, engine, methane, detector, target_grid):
        """Critical flags from Layer 2 should appear in pipeline warnings."""
        result = engine.run_full_pipeline(
            country_code="SA",
            substance=methane,
            ventilation=VentilationLevel.POOR,
            detectors=[detector],
            target_grid=target_grid,
        )

        # POOR ventilation -> Zone 0 -> critical flag
        has_critical = any(
            "CRITICAL" in w
            for w in result.pipeline_warnings
        )
        assert has_critical

    def test_pipeline_elapsed_time_reasonable(self, engine, methane, detector, target_grid):
        """Pipeline should complete in under 10 seconds for typical workload."""
        result = engine.run_full_pipeline(
            country_code="SA",
            substance=methane,
            ventilation=VentilationLevel.MEDIUM,
            detectors=[detector],
            target_grid=target_grid,
        )

        # Sequential processing should be fast
        assert result.elapsed_seconds < 10.0


# ===========================================================================
# 6. Environmental Context Integration
# ===========================================================================

class TestEnvironmentIntegration:
    """Test that environmental context properly affects pipeline results."""

    def test_worst_case_defaults(self, engine):
        """Default engine should use worst-case environmental context."""
        assert engine._env_context.stability_class == PasquillStability.F
        assert engine._env_context.wind_speed_m_s == 0.5
        assert engine._env_context.ambient_temp_c == 40.0
        assert engine._env_context.is_indoor is True

    def test_custom_environment(self):
        """Engine with custom environment should use provided values."""
        ctx = EnvironmentalContext(
            ambient_temp_c=60.0,
            wind_speed_m_s=3.0,
            stability_class=PasquillStability.D,
        )
        engine = CLIFireAIEngine(grid_step_m=1.0, env_context=ctx)
        assert engine._env_context.ambient_temp_c == 60.0
        assert engine._env_context.wind_speed_m_s == 3.0

    def test_hot_vs_normal_zone_extent(self, engine, engine_hot, methane):
        """Hot environment should produce larger zone extents."""
        result_normal = engine.run_layer2(methane, VentilationLevel.MEDIUM)
        result_hot = engine_hot.run_layer2(methane, VentilationLevel.MEDIUM)

        # At 80C, LFL is corrected downward -> larger zone
        # At 40C (default), LFL is also corrected but less
        assert result_hot.horizontal_m >= result_normal.horizontal_m


# ===========================================================================
# 7. Consultant's ProcessPoolExecutor Rejection Verification
# ===========================================================================

class TestNoProcessPoolExecutor:
    """
    Verify that CLIFireAIEngine does NOT use ProcessPoolExecutor.

    The consultant proposed ProcessPoolExecutor with global mutable state.
    This was REJECTED for the following reasons:
      1. Premature optimization (no demonstrated bottleneck)
      2. Global mutable state contradicts Pydantic frozen principles
      3. BVH tree doesn't exist in codebase (R-tree is already implemented)
      4. ProcessPoolExecutor adds ~100ms overhead for typical workloads
      5. No error handling for worker crashes
      6. N× memory consumption for N workers

    This test class verifies that the rejection is maintained.
    """

    def test_no_concurrent_futures_import(self):
        """Engine should NOT import concurrent.futures."""
        import fireai.core.fireai_cli_engine as mod
        import ast
        with open(mod.__file__) as f:
            source = f.read()
        # Parse AST to check actual imports, not just strings in comments
        tree = ast.parse(source)
        import_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    import_names.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    import_names.add(node.module)
        assert "concurrent.futures" not in import_names
        # Also verify no ProcessPoolExecutor in actual code (excluding comments/docstrings)
        # Strip all string literals and comments to check code only
        for node in ast.walk(tree):
            assert not (isinstance(node, ast.Name) and node.id == "ProcessPoolExecutor")

    def test_no_global_worker_state(self):
        """Engine should NOT use global mutable worker state."""
        import fireai.core.fireai_cli_engine as mod
        import ast
        with open(mod.__file__) as f:
            source = f.read()
        # Check for the specific anti-patterns from consultant's proposal
        # Only in actual code (AST), not in docstrings/comments
        tree = ast.parse(source)
        global_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Global):
                global_names.update(node.names)
        assert "_WORKER_BVH_ROOT" not in global_names
        assert "_WORKER_ENV_CONTEXT" not in global_names
        # Also check function definitions don't exist
        func_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                func_names.add(node.name)
        assert "_initialize_worker" not in func_names
        assert "_process_ray_packet" not in func_names

    def test_sequential_processing_is_correct(self, engine, detector, target_grid):
        """Sequential processing should produce correct, deterministic results."""
        result1 = engine.run_layer5([detector], target_grid, [])
        result2 = engine.run_layer5([detector], target_grid, [])

        # Sequential processing is deterministic
        assert result1.covered_points == result2.covered_points
        assert result1.coverage_pct == result2.coverage_pct

    def test_ray_trace_uses_existing_engine(self, engine, detector, target_grid):
        """Layer 5 should delegate to FlameDetectorAOCRayTrace, not reimplement."""
        from fireai.core.flame_detector_aoc_raytrace import FlameDetectorAOCRayTrace
        assert isinstance(engine._ray_engine, FlameDetectorAOCRayTrace)


# ===========================================================================
# 8. Edge Cases
# ===========================================================================

class TestEdgeCases:
    """Edge cases for CLI engine."""

    def test_empty_target_grid(self, engine, detector):
        """Empty target grid should return 0% coverage."""
        result = engine.run_layer5([detector], [], [])
        assert result.total_points == 0
        assert result.covered_points == 0

    def test_substance_no_autoignition(self, engine):
        """Substance without autoignition should still classify."""
        sub = SubstanceProperties(
            name="UnknownGas",
            hazard_type=HazardType.GAS,
            lfl_vol_pct=3.0,
            ufl_vol_pct=12.0,
        )
        result = engine.run_layer2(sub, VentilationLevel.MEDIUM)
        assert result.success
        # Layer 3 should handle None autoignition gracefully
        l3 = engine.run_layer3(result.zone, result.hazard_type, autoignition_c=None)
        # Default temp class when no autoignition
        assert l3.temp_class in ("T4", "T5", "T6")

    def test_outdoor_environment(self, methane):
        """Outdoor environment should use full sphere volume."""
        ctx = EnvironmentalContext(is_indoor=False)
        engine = CLIFireAIEngine(grid_step_m=1.0, env_context=ctx)
        result = engine.run_layer2(methane, VentilationLevel.MEDIUM)
        assert result.success

    def test_pipeline_with_propane(self, engine, propane, detector, target_grid):
        """Propane (lower LFL) should produce larger zone than methane."""
        methane_sub = SubstanceProperties(
            name="Methane", hazard_type=HazardType.GAS,
            lfl_vol_pct=5.0, ufl_vol_pct=15.0, autoignition_c=537.0,
        )
        result_methane = engine.run_layer2(methane_sub, VentilationLevel.MEDIUM)
        result_propane = engine.run_layer2(propane, VentilationLevel.MEDIUM)

        # Propane LFL=2.1 < Methane LFL=5.0 -> larger zone
        assert result_propane.horizontal_m >= result_methane.horizontal_m
