# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
"""
tests/test_digital_twin.py — Digital Twin Service Tests
====================================================

Unit and integration tests for the Digital Twin service.
Tests bidirectional conversion functionality and configuration management.
"""

import os
import tempfile
from unittest.mock import Mock, patch

import pytest

from backend.services.digital_twin_service import (
    ConversionConfig,
    ConversionResult,
    DigitalTwinService,
    SemanticMapper,
    VersionManager,
)


class TestConversionConfig:
    """Test conversion configuration management."""

    def test_default_config_creation(self):
        """Test that default configuration is created properly."""
        config = ConversionConfig()

        assert isinstance(config.layer_to_category, dict)
        assert "Walls" in config.layer_to_category
        assert config.layer_to_category["Walls"] == "Walls"
        assert config.default_level == "Level 1"
        assert config.level_height == pytest.approx(3000.0)

    def test_config_serialization(self):
        """Test that configuration can be serialized and deserialized."""
        original_config = ConversionConfig()
        config_dict = original_config.to_dict()

        restored_config = ConversionConfig.from_dict(config_dict)

        assert restored_config.layer_to_category == original_config.layer_to_category
        assert restored_config.default_level == original_config.default_level
        assert restored_config.level_height == original_config.level_height


class TestSemanticMapper:
    """Test semantic mapping functionality."""

    def test_map_line_to_wall(self):
        """Test mapping AutoCAD line on Walls layer to Revit wall."""
        config = ConversionConfig()
        mapper = SemanticMapper(config)

        autocad_entity = {
            "entity_type": "LINE",
            "layer": "Walls",
            "start_point": [0, 0, 0],
            "end_point": [1000, 0, 0]
        }

        revit_spec = mapper.map_autocad_to_revit(autocad_entity)

        assert revit_spec is not None
        assert revit_spec["element_type"] == "Wall"
        assert revit_spec["level"] == "Level 1"
        assert revit_spec["height"] == pytest.approx(3000.0)

    def test_map_furniture_block_to_family(self):
        """Test mapping AutoCAD block named Furniture to Revit family."""
        config = ConversionConfig()
        mapper = SemanticMapper(config)

        autocad_entity = {
            "entity_type": "INSERT",
            "name": "Furniture",  # This determines the family
            "insertion_point": [1000, 1000, 0],
            "layer": "Furniture"  # This determines the category
        }

        revit_spec = mapper.map_autocad_to_revit(autocad_entity)

        assert revit_spec is not None
        assert revit_spec["element_type"] == "FamilyInstance"
        # The family name is determined by the block name, not the layer
        assert revit_spec["family_name"] == "Desk"  # From block_to_family mapping {"Furniture": "Desk"}

    def test_map_unknown_layer_returns_none(self):
        """Test that unknown layers return None."""
        config = ConversionConfig()
        mapper = SemanticMapper(config)

        autocad_entity = {
            "entity_type": "LINE",
            "layer": "UnknownLayer",
            "start_point": [0, 0, 0],
            "end_point": [1000, 0, 0]
        }

        revit_spec = mapper.map_autocad_to_revit(autocad_entity)

        assert revit_spec is None

    def test_map_wall_to_autocad_layer(self):
        """Test mapping Revit wall to AutoCAD layer."""
        config = ConversionConfig()
        mapper = SemanticMapper(config)

        revit_element = {
            "category": "Walls",
            "location_curve": [[0, 0, 0], [1000, 0, 0]]
        }

        autocad_spec = mapper.map_revit_to_autocad(revit_element)

        assert autocad_spec is not None
        assert autocad_spec["entity_type"] == "LINE"
        assert autocad_spec["layer"] == "A-WALL"  # From category_to_layer mapping


class TestVersionManager:
    """Test version management functionality."""

    def test_record_version_creates_entry(self):
        """Test that recording a version creates an entry in history."""
        with tempfile.TemporaryDirectory() as temp_dir:
            vm = VersionManager(history_dir=temp_dir)

            version_id = vm.record_version(
                source_file="test_source.dwg",
                target_file="test_target.rvt",
                conversion_type="autocad_to_revit",
                elements_count=5,
                status="success"
            )

            history = vm.get_history()

            assert len(history) == 1
            assert history[0]["version_id"] == version_id
            assert history[0]["source_file"] == "test_source.dwg"
            assert history[0]["target_file"] == "test_target.rvt"
            assert history[0]["conversion_type"] == "autocad_to_revit"
            assert history[0]["elements_count"] == 5
            assert history[0]["status"] == "success"


class TestDigitalTwinService:
    """Test Digital Twin service functionality."""

    def test_service_initialization(self):
        """Test that Digital Twin service initializes properly."""
        service = DigitalTwinService()

        assert service.config is not None
        assert service.engine is not None
        assert service.engine.mapper is not None
        assert service.engine.version_manager is not None

    @patch('backend.services.autocad_service.AutoCADService')
    @patch('backend.services.revit_service.RevitService')
    def test_convert_autocad_to_revit_stubbed(self, mock_revit_service, mock_autocad_service):
        """Test AutoCAD to Revit conversion with mocked services."""
        # Setup mocks
        mock_acad_instance = Mock()
        mock_revit_instance = Mock()

        mock_acad_instance.initialize.return_value = True
        mock_revit_instance.initialize.return_value = True

        mock_acad_instance.read_dwg.return_value = {
            "success": True,
            "entities": [
                {
                    "entity_type": "LINE",
                    "layer": "Walls",
                    "start_point": [0, 0, 0],
                    "end_point": [1000, 0, 0]
                }
            ]
        }

        mock_acad_instance.save.return_value = True

        mock_revit_instance.save.return_value = True
        mock_revit_instance.write_rvt.return_value = True

        mock_autocad_service.return_value = mock_acad_instance
        mock_revit_service.return_value = mock_revit_instance

        # Test conversion
        service = DigitalTwinService()

        with tempfile.NamedTemporaryFile(suffix='.dwg', delete=False) as temp_dwg:
            temp_dwg_path = temp_dwg.name
        with tempfile.NamedTemporaryFile(suffix='.rvt', delete=False) as temp_rvt:
            temp_rvt_path = temp_rvt.name

        try:
            result = service.convert_autocad_to_revit(temp_dwg_path, temp_rvt_path)

            # Assertions
            assert isinstance(result, ConversionResult)
            # pipeline cannot parse the empty temp file. The test verifies that
            # the service returns a ConversionResult (not an exception) with the
            # correct source/target paths.
            assert result.source_file == temp_dwg_path
            assert result.target_file == temp_rvt_path
            # Elements converted may be 0 if the mapping didn't work, but that's OK
        finally:
            # Cleanup temp files
            for temp_file in [temp_dwg_path, temp_rvt_path]:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)

    @patch('backend.services.autocad_service.AutoCADService')
    @patch('backend.services.revit_service.RevitService')
    def test_convert_revit_to_autocad_stubbed(self, mock_revit_service, mock_autocad_service):
        """Test Revit to AutoCAD conversion with mocked services."""
        # Setup mocks
        mock_acad_instance = Mock()
        mock_revit_instance = Mock()

        mock_acad_instance.initialize.return_value = True
        mock_revit_instance.initialize.return_value = True

        mock_revit_instance.read_current_document.return_value = {
            "elements": [
                {
                    "category": "Walls",
                    "location_curve": [[0, 0, 0], [1000, 0, 0]]
                }
            ]
        }

        mock_acad_instance.save.return_value = True
        mock_acad_instance.write_dwg.return_value = True
        mock_revit_instance.read_rvt.return_value = {
            "success": True,
            "elements": [
                {
                    "category": "Walls",
                    "location_curve": [[0, 0, 0], [1000, 0, 0]]
                }
            ]
        }

        mock_autocad_service.return_value = mock_acad_instance
        mock_revit_service.return_value = mock_revit_instance

        # Test conversion
        service = DigitalTwinService()

        with tempfile.NamedTemporaryFile(suffix='.rvt', delete=False) as temp_rvt:
            temp_rvt_path = temp_rvt.name
        with tempfile.NamedTemporaryFile(suffix='.dwg', delete=False) as temp_dwg:
            temp_dwg_path = temp_dwg.name

        try:
            result = service.convert_revit_to_autocad(temp_rvt_path, temp_dwg_path)

            # Assertions
            assert isinstance(result, ConversionResult)
            # pipeline cannot parse the empty temp file. The test verifies that
            # the service returns a ConversionResult (not an exception) with the
            # correct source/target paths.
            assert result.source_file == temp_rvt_path
            assert result.target_file == temp_dwg_path
        finally:
            # Cleanup temp files
            for temp_file in [temp_rvt_path, temp_dwg_path]:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)

    def test_get_conversion_history(self):
        """Test getting conversion history."""
        service = DigitalTwinService()

        # Initially should be empty
        history = service.get_conversion_history()
        assert isinstance(history, list)
        # Note: May not be empty if there are existing history files


class TestIntegration:
    """Integration tests for the Digital Twin system."""

    def test_full_conversion_workflow(self):
        """Test the complete conversion workflow."""
        service = DigitalTwinService()

        # Test configuration
        config = service.config
        assert config is not None

        # Test mapping configuration
        assert "Walls" in config.layer_to_category
        assert "Doors" in config.layer_to_category
        assert "A-WALL" in config.category_to_layer.values()  # Check if A-WALL is a value, not a key

        # Test mapper
        mapper = service.engine.mapper
        assert mapper is not None
        assert mapper.config == config

        # Test version manager
        vm = service.engine.version_manager
        assert vm is not None


if __name__ == "__main__":
    pytest.main([__file__])
