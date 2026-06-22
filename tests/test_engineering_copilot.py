"""
ETAP-AI-WORK Engineering Copilot Tests
====================================

Tests for the Engineering Copilot functionality.

Principal Software Architect: Eng. Ahmed Elbaz
"""
import pytest
import asyncio
from datetime import datetime
from typing import Dict, Any

from engineering_copilot.ai_agent.ai_agent import AICopilot, EngineeringIntentProcessor
from engineering_copilot.translation_engine.translation_engine import TranslationEngine
from engineering_copilot.models.unified_model import (
    UnifiedEngineeringModel, Panel, Transformer, Bus, Cable, 
    Breaker, Load, Generator, Equipment, Coordinates, EntityType
)


@pytest.fixture
def ai_copilot():
    """Create an AI Copilot instance for testing."""
    return AICopilot()


@pytest.fixture
def intent_processor():
    """Create an intent processor instance for testing."""
    return EngineeringIntentProcessor()


@pytest.fixture
def translation_engine():
    """Create a translation engine instance for testing."""
    return TranslationEngine()


@pytest.mark.asyncio
async def test_intent_processor_basic():
    """Test basic intent processing."""
    processor = EngineeringIntentProcessor()
    
    request = "Create a main distribution board with 5 outgoing feeders"
    intent = processor.parse_intent(request)
    
    assert "entities" in intent
    assert len(intent["entities"]) > 0
    
    # Check if panel was detected
    panel_entities = [e for e in intent["entities"] if e["type"] == "panel"]
    assert len(panel_entities) >= 1
    
    print(f"Detected {len(intent['entities'])} entities from request: {request}")


@pytest.mark.asyncio
async def test_intent_processor_transformer():
    """Test transformer intent processing."""
    processor = EngineeringIntentProcessor()
    
    request = "Add a 1000kVA transformer with 13.8kV primary and 480V secondary"
    intent = processor.parse_intent(request)
    
    transformer_entities = [e for e in intent["entities"] if e["type"] == "transformer"]
    assert len(transformer_entities) >= 1
    
    # Check if power rating was detected
    if "powers" in intent and len(intent["powers"]) > 0:
        assert intent["powers"][0]["value_kw"] == 1000.0
    
    print(f"Detected transformer with power rating: {intent.get('powers', [])}")


@pytest.mark.asyncio
async def test_ai_copilot_process_request(ai_copilot):
    """Test AI Copilot processing a basic request."""
    request = "Create a MDB panel with 5 outgoing feeders and 1 transformer."
    result = ai_copilot.process_request(request, ["AutoCAD", "ETAP"])
    
    assert "unified_model" in result
    assert "generated_models" in result
    assert "AutoCAD" in result["generated_models"]
    assert "ETAP" in result["generated_models"]
    
    # Check that the model has entities
    model = result["unified_model"]
    assert len(model.entities) > 0
    
    print(f"Generated unified model with {len(model.entities)} entities")


@pytest.mark.asyncio
async def test_translation_engine_etap_to_unified(translation_engine):
    """Test ETAP to Unified Model translation."""
    # Create mock ETAP data
    etap_data = {
        "buses": [
            {"id": "bus_1", "name": "Main Bus", "voltage": 13800.0, "rated_current": 2000.0}
        ],
        "transformers": [
            {"id": "xfmer_1", "name": "Main Transformer", "primary_voltage": 13800.0, "secondary_voltage": 480.0, "power_rating": 1000.0}
        ],
        "panels": [
            {"id": "panel_1", "name": "MDB", "voltage_rating": 480.0, "current_rating": 400.0, "feeder_count": 5}
        ]
    }
    
    unified_model = translation_engine.etap_to_unified(etap_data)
    
    assert len(unified_model.entities) == 3  # 1 bus, 1 transformer, 1 panel
    
    # Check that entities were created correctly
    buses = unified_model.get_entities_by_type(EntityType.BUS)
    transformers = unified_model.get_entities_by_type(EntityType.TRANSFORMER)
    panels = unified_model.get_entities_by_type(EntityType.PANEL)
    
    assert len(buses) == 1
    assert len(transformers) == 1
    assert len(panels) == 1
    
    print(f"Translated ETAP data to unified model with {len(unified_model.entities)} entities")


@pytest.mark.asyncio
async def test_translation_engine_unified_to_autocad(translation_engine):
    """Test Unified Model to AutoCAD translation."""
    # Create a simple unified model
    model = UnifiedEngineeringModel()
    
    panel = Panel(
        id="panel_1",
        name="MDB Panel",
        description="Main Distribution Board",
        voltage_rating=480.0,
        current_rating=400.0,
        feeder_count=5,
        coordinates=Coordinates(10.0, 10.0)
    )
    
    transformer = Transformer(
        id="transformer_1",
        name="Main Transformer",
        description="Main step-down transformer",
        primary_voltage=13800.0,
        secondary_voltage=480.0,
        power_rating=1000.0,
        coordinates=Coordinates(15.0, 15.0)
    )
    
    model.add_entity(panel)
    model.add_entity(transformer)
    
    autocad_ops = translation_engine.unified_to_autocad(model)
    
    assert "insert_blocks" in autocad_ops
    assert len(autocad_ops["insert_blocks"]) >= 2  # panel and transformer
    
    print(f"Translated unified model to {len(autocad_ops['insert_blocks'])} AutoCAD operations")


@pytest.mark.asyncio
async def test_unified_model_creation():
    """Test creating and manipulating unified models."""
    model = UnifiedEngineeringModel()
    
    # Add a panel
    panel = Panel(
        id="panel_1",
        name="Test Panel",
        description="Test panel for validation",
        voltage_rating=480.0,
        current_rating=400.0,
        feeder_count=3,
        coordinates=Coordinates(0.0, 0.0)
    )
    model.add_entity(panel)
    
    # Add a transformer
    transformer = Transformer(
        id="transformer_1",
        name="Test Transformer",
        description="Test transformer for validation",
        primary_voltage=13800.0,
        secondary_voltage=480.0,
        power_rating=500.0,
        coordinates=Coordinates(5.0, 5.0)
    )
    model.add_entity(transformer)
    
    # Verify entities were added
    assert len(model.entities) == 2
    
    # Get entities by type
    panels = model.get_entities_by_type(EntityType.PANEL)
    transformers = model.get_entities_by_type(EntityType.TRANSFORMER)
    
    assert len(panels) == 1
    assert len(transformers) == 1
    
    # Get entity by ID
    retrieved_panel = model.get_entity_by_id("panel_1")
    assert retrieved_panel is not None
    assert retrieved_panel.name == "Test Panel"
    
    print(f"Created unified model with {len(model.entities)} entities")


@pytest.mark.asyncio
async def test_engineering_validation(ai_copilot):
    """Test engineering model validation."""
    model = UnifiedEngineeringModel()
    
    # Add valid entities
    panel = Panel(
        id="panel_1",
        name="Valid Panel",
        voltage_rating=480.0,
        current_rating=400.0,
        feeder_count=5,
        coordinates=Coordinates(0.0, 0.0)
    )
    model.add_entity(panel)
    
    # Add a transformer
    transformer = Transformer(
        id="transformer_1",
        name="Valid Transformer",
        primary_voltage=13800.0,
        secondary_voltage=480.0,
        power_rating=1000.0,
        coordinates=Coordinates(5.0, 5.0)
    )
    model.add_entity(transformer)
    
    # Perform validation
    validation_report = ai_copilot._validate_engineering_model(model)
    
    assert "errors" in validation_report
    assert "warnings" in validation_report
    assert "passed" in validation_report
    
    # Should pass validation since all required values are valid
    assert validation_report["passed"] == True
    
    print(f"Validation completed: {validation_report['summary']}")


@pytest.mark.asyncio
async def test_report_generation(ai_copilot):
    """Test engineering report generation."""
    model = UnifiedEngineeringModel()
    
    # Add entities for report generation
    panel = Panel(
        id="panel_1",
        name="Report Panel",
        voltage_rating=480.0,
        current_rating=400.0,
        feeder_count=5,
        coordinates=Coordinates(0.0, 0.0)
    )
    model.add_entity(panel)
    
    transformer = Transformer(
        id="transformer_1",
        name="Report Transformer",
        primary_voltage=13800.0,
        secondary_voltage=480.0,
        power_rating=1000.0,
        coordinates=Coordinates(5.0, 5.0)
    )
    model.add_entity(transformer)
    
    # Generate reports
    reports = ai_copilot.generate_reports(model)
    
    assert "bom" in reports
    assert "panel_schedule" in reports
    assert "electrical_schedule" in reports
    assert "design_documentation" in reports
    
    # Check BOM has entries
    assert len(reports["bom"]) >= 2  # panel and transformer
    
    # Check panel schedule
    assert len(reports["panel_schedule"]) >= 1
    
    print(f"Generated reports: BOM with {len(reports['bom'])} items, {len(reports['panel_schedule'])} panels")


@pytest.mark.asyncio
async def test_complex_request_processing(ai_copilot):
    """Test processing a complex engineering request."""
    complex_request = """
    Design a main electrical distribution system with:
    - One 1500kVA transformer (13.8kV/480V)
    - One main distribution board (MDB) with 8 feeders
    - Two sub-panels with 6 feeders each
    - Connect the sub-panels to the MDB with 500kcmil copper cables
    - All equipment rated for 480V system
    """
    
    result = ai_copilot.process_request(complex_request, ["AutoCAD", "ETAP", "Revit"])
    
    assert "unified_model" in result
    assert "generated_models" in result
    assert "validation_report" in result
    
    model = result["unified_model"]
    assert len(model.entities) >= 4  # transformer, mdb, 2 sub-panels
    
    # Count different entity types
    panels = model.get_entities_by_type(EntityType.PANEL)
    transformers = model.get_entities_by_type(EntityType.TRANSFORMER)
    
    assert len(panels) >= 3  # mdb + 2 sub-panels
    assert len(transformers) >= 1  # main transformer
    
    print(f"Complex request generated {len(model.entities)} entities")


@pytest.mark.asyncio
async def test_conflict_detection(ai_copilot):
    """Test conflict detection in engineering models."""
    model = UnifiedEngineeringModel()
    
    # Add entities that might have conflicts
    panel1 = Panel(
        id="panel_1",
        name="Panel 1",
        voltage_rating=480.0,
        current_rating=400.0,
        feeder_count=50,  # Too many feeders for typical panel
        coordinates=Coordinates(0.0, 0.0)
    )
    model.add_entity(panel1)
    
    # Add same coordinates to create overlap
    panel2 = Panel(
        id="panel_2",
        name="Panel 2",
        voltage_rating=480.0,
        current_rating=400.0,
        feeder_count=3,
        coordinates=Coordinates(0.0, 0.0)  # Same as panel1
    )
    model.add_entity(panel2)
    
    # Detect conflicts
    conflicts = ai_copilot.detect_conflicts(model)
    
    # Should detect coordinate overlap and panel overloading
    assert len(conflicts) >= 1
    
    print(f"Detected {len(conflicts)} conflicts in the model")


@pytest.mark.asyncio
async def test_entity_relationships():
    """Test entity relationships in unified model."""
    model = UnifiedEngineeringModel()
    
    # Create entities
    transformer = Transformer(
        id="transformer_1",
        name="Main Transformer",
        primary_voltage=13800.0,
        secondary_voltage=480.0,
        power_rating=1000.0,
        coordinates=Coordinates(0.0, 0.0)
    )
    
    panel = Panel(
        id="panel_1",
        name="Main Panel",
        voltage_rating=480.0,
        current_rating=400.0,
        feeder_count=5,
        coordinates=Coordinates(5.0, 5.0)
    )
    
    # Add relationships
    from engineering_copilot.models.unified_model import Relationship
    panel.relationships.append(Relationship(
        type="feeds",
        entity_id="transformer_1",
        relationship="fed_by"
    ))
    
    model.add_entity(transformer)
    model.add_entity(panel)
    
    # Test relationship functionality
    related_entities = model.get_related_entities("transformer_1")
    assert len(related_entities) >= 1
    
    print(f"Found {len(related_entities)} entities related to transformer")


if __name__ == "__main__":
    pytest.main([__file__])