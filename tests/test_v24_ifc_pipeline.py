"""
tests/test_v24_ifc_pipeline.py
================================
Tests for GAP-1: IfcFirePipeline module import and configuration.
The pipeline requires an IFC file to run, so we test:
  - Module import
  - Configuration creation
  - Bridge new methods (extract_storeys, extract_obstructions, extract_spaces_enhanced)
  - Pipeline class instantiation

Run: pytest tests/test_v24_ifc_pipeline.py -v
"""

import pytest

from fireai.bridges.ifc_pipeline import (
    IfcFirePipeline,
    IfcPipelineConfig,
    SpaceAnalysisResult,
    PipelineReport,
)
from fireai.bridges.ifc_headless_bridge import HeadlessIFCBridge


class TestIfcPipelineConfig:
    """Test IfcPipelineConfig dataclass."""

    def test_default_config(self):
        """Default config should have sensible values."""
        cfg = IfcPipelineConfig(
            ifc_input_path="test.ifc",
            ifc_output_path="test_output.ifc",
        )
        assert cfg.country_code == "SA"
        assert cfg.substance_cas == "74-98-6"  # propane
        assert cfg.ventilation == "MEDIUM"
        assert cfg.flame_range_m == 15.0
        assert cfg.ambient_temp_c == 40.0
        assert cfg.is_indoor is True

    def test_custom_config(self):
        """Custom config values should be accepted."""
        cfg = IfcPipelineConfig(
            ifc_input_path="building.ifc",
            ifc_output_path="building_output.ifc",
            country_code="DE",
            substance_cas="74-82-8",  # methane
            ventilation="POOR",
            ambient_temp_c=25.0,
        )
        assert cfg.country_code == "DE"
        assert cfg.substance_cas == "74-82-8"
        assert cfg.ventilation == "POOR"
        assert cfg.ambient_temp_c == 25.0


class TestIfcPipelineInstantiation:
    """Test IfcFirePipeline class instantiation."""

    def test_pipeline_creation(self):
        """Pipeline should be creatable with a config."""
        cfg = IfcPipelineConfig(
            ifc_input_path="test.ifc",
            ifc_output_path="test_output.ifc",
        )
        pipeline = IfcFirePipeline(cfg)
        assert pipeline.cfg is cfg

    def test_pipeline_has_run_method(self):
        """Pipeline must have a run() method."""
        cfg = IfcPipelineConfig(
            ifc_input_path="test.ifc",
            ifc_output_path="test_output.ifc",
        )
        pipeline = IfcFirePipeline(cfg)
        assert hasattr(pipeline, "run")
        assert callable(pipeline.run)


class TestSpaceAnalysisResult:
    """Test SpaceAnalysisResult dataclass."""

    def test_creation(self):
        """Should create a result with all fields."""
        result = SpaceAnalysisResult(
            space_guid="test-guid",
            space_name="Room 101",
            storey_name="Ground Floor",
            layer1_framework="IECEx",
            layer2_zone="ZONE_1",
            layer2_extent_h=6.0,
            layer2_extent_v=3.0,
            layer3_epl="Gb",
            layer3_tclass="T3",
            layer3_protections=["ib"],
            layer5_coverage_pct=85.5,
            layer7_redundant_pct=60.0,
            layer7_blind_spot_pct=5.0,
            detector_placements=[],
            warnings=["test warning"],
        )
        assert result.space_guid == "test-guid"
        assert result.layer2_zone == "ZONE_1"
        assert result.layer5_coverage_pct == 85.5
        assert result.layer7_blind_spot_pct == 5.0


class TestPipelineReport:
    """Test PipelineReport dataclass."""

    def test_creation(self):
        """Should create a report with all fields."""
        report = PipelineReport(
            ifc_input="test.ifc",
            ifc_output="test_output.ifc",
            heatmap_path="test_heatmap.json",
            run_time_s=1.5,
            spaces_analysed=5,
            total_detectors=20,
            global_coverage_pct=85.0,
            global_blind_spot_pct=3.0,
            space_results=[],
            pipeline_warnings=[],
        )
        assert report.spaces_analysed == 5
        assert report.total_detectors == 20
        assert report.heatmap_path == "test_heatmap.json"


class TestBridgeNewMethods:
    """Test that the bridge has the new GAP-1 methods."""

    def test_bridge_has_extract_storeys(self):
        """Bridge must have extract_storeys() method."""
        assert hasattr(HeadlessIFCBridge, "extract_storeys")

    def test_bridge_has_extract_obstructions(self):
        """Bridge must have extract_obstructions() method."""
        assert hasattr(HeadlessIFCBridge, "extract_obstructions")

    def test_bridge_has_extract_spaces_enhanced(self):
        """Bridge must have extract_spaces_enhanced() method."""
        assert hasattr(HeadlessIFCBridge, "extract_spaces_enhanced")

    def test_bridge_preserves_extract_spaces(self):
        """Original extract_spaces() must still exist (backward compat)."""
        assert hasattr(HeadlessIFCBridge, "extract_spaces")

    def test_bridge_preserves_push_fire_alarm_design(self):
        """Original push_fire_alarm_design() must still exist."""
        assert hasattr(HeadlessIFCBridge, "push_fire_alarm_design")

    def test_bridge_has_obstruction_types(self):
        """Bridge must define OBSTRUCTION_TYPES for ray-tracing."""
        assert hasattr(HeadlessIFCBridge, "OBSTRUCTION_TYPES")
        assert "IfcWall" in HeadlessIFCBridge.OBSTRUCTION_TYPES
        assert "IfcBeam" in HeadlessIFCBridge.OBSTRUCTION_TYPES
        assert "IfcDuctSegment" in HeadlessIFCBridge.OBSTRUCTION_TYPES
        assert "IfcSlab" in HeadlessIFCBridge.OBSTRUCTION_TYPES


class TestPipelineSubstanceLookup:
    """Test that the pipeline can resolve substance properties."""

    def test_propane_cas_resolves(self):
        """Pipeline should resolve propane CAS to SubstanceProperties."""
        cfg = IfcPipelineConfig(
            ifc_input_path="test.ifc",
            ifc_output_path="test_output.ifc",
            substance_cas="74-98-6",
        )
        pipeline = IfcFirePipeline(cfg)
        substance = pipeline._get_substance()
        assert substance.name == "Propane"
        assert substance.lfl_vol_pct == 2.1
        assert substance.autoignition_c == 450.0  # NFPA 497-2024 Table 4.4.2

    def test_methane_cas_resolves(self):
        """Pipeline should resolve methane CAS."""
        cfg = IfcPipelineConfig(
            ifc_input_path="test.ifc",
            ifc_output_path="test_output.ifc",
            substance_cas="74-82-8",
        )
        pipeline = IfcFirePipeline(cfg)
        substance = pipeline._get_substance()
        assert substance.name == "Methane"

    def test_unknown_cas_defaults_to_propane(self):
        """Unknown CAS should default to propane properties."""
        cfg = IfcPipelineConfig(
            ifc_input_path="test.ifc",
            ifc_output_path="test_output.ifc",
            substance_cas="UNKNOWN-CAS",
        )
        pipeline = IfcFirePipeline(cfg)
        substance = pipeline._get_substance()
        assert substance.lfl_vol_pct == 2.1  # Propane default


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
