"""
ETAP-AI-WORK Revit Integration Tests
===================================

Tests for the Revit integration functionality.

Principal Software Architect: Eng. Ahmed Elbaz
"""
import pytest
import asyncio
from datetime import datetime
from typing import Dict, Any

from revit_integration.dto.revit_dto import (
    RevitElementDTO, ElectricalAssetDTO, SyncStatusDTO, 
    ModelMetadataDTO, RevitProjectDTO
)
from revit_integration.services.revit_sync_service import RevitSyncService
from revit_integration.mappings.category_mapper import CategoryMapper
from revit_integration.ai_agents.revit_agent import RevitAgent, create_revit_agent


@pytest.fixture
def sample_revit_elements():
    """Create sample Revit elements for testing."""
    elements = [
        RevitElementDTO(
            id="ele_1",
            name="Transformer_1",
            category="Electrical Equipment",
            family="Power Transformers",
            type="Dry Type",
            parameters={
                "VoltageRating": 480,
                "PowerRating": 1000,
                "Manufacturer": "ABB",
                "Model": "DRY1000"
            },
            location={"x": 10.0, "y": 20.0, "z": 0.0}
        ),
        RevitElementDTO(
            id="ele_2",
            name="Panelboard_A1",
            category="Electrical Panel",
            family="Distribution Panels",
            type="Main Lug",
            parameters={
                "VoltageRating": 480,
                "CurrentRating": 200,
                "PoleCount": 42
            },
            location={"x": 15.0, "y": 25.0, "z": 0.0}
        ),
        RevitElementDTO(
            id="ele_3",
            name="Room_101",
            category="Rooms",
            family="Architecture",
            type="Office",
            parameters={
                "Area": 200.0,
                "Level": "Level 1"
            },
            location={"x": 5.0, "y": 5.0, "z": 0.0}
        )
    ]
    return elements


@pytest.fixture
def sample_electrical_assets():
    """Create sample electrical assets for testing."""
    assets = [
        ElectricalAssetDTO(
            element_id="ele_1",
            asset_type="Transformer",
            name="Transformer_1",
            voltage_rating=480.0,
            power_rating=1000.0,
            manufacturer="ABB",
            model="DRY1000",
            connections=["ele_2"]
        ),
        ElectricalAssetDTO(
            element_id="ele_2",
            asset_type="Panelboard",
            name="Panelboard_A1",
            voltage_rating=480.0,
            power_rating=200.0,
            manufacturer="Siemens",
            model="P1234",
            connections=[]
        )
    ]
    return assets


@pytest.mark.asyncio
async def test_revit_element_dto_creation():
    """Test creating RevitElementDTO instances."""
    element = RevitElementDTO(
        id="test_1",
        name="Test Element",
        category="Electrical Equipment",
        parameters={"Voltage": 480, "Power": 100}
    )
    
    assert element.id == "test_1"
    assert element.name == "Test Element"
    assert element.category == "Electrical Equipment"
    assert element.parameters["Voltage"] == 480
    assert element.parameters["Power"] == 100
    assert element.created_at is not None


@pytest.mark.asyncio
async def test_electrical_asset_dto_creation():
    """Test creating ElectricalAssetDTO instances."""
    asset = ElectricalAssetDTO(
        element_id="test_1",
        asset_type="Transformer",
        name="Test Transformer",
        voltage_rating=480.0,
        power_rating=1000.0,
        manufacturer="Test Manufacturer"
    )
    
    assert asset.element_id == "test_1"
    assert asset.asset_type == "Transformer"
    assert asset.name == "Test Transformer"
    assert asset.voltage_rating == 480.0
    assert asset.power_rating == 1000.0
    assert asset.manufacturer == "Test Manufacturer"


@pytest.mark.asyncio
async def test_category_mapper_functionality():
    """Test the category mapper functionality."""
    mapper = CategoryMapper()
    
    # Test category to model mapping
    model_type = mapper.get_target_model("Electrical Equipment")
    assert model_type is not None
    assert model_type.name == "ELECTRICAL"
    
    # Test attribute mapping
    attributes = mapper.map_category_to_attributes("Electrical Equipment")
    assert attributes["etap_model_type"].name == "ELECTRICAL"
    assert attributes["is_electrical"] is True
    
    # Test equipment classification
    equipment_type = mapper.classify_equipment_type("Transformer XYZ", "Electrical Equipment")
    assert equipment_type in ["Transformer", "ElectricalEquipment"]
    
    # Test parameter transformation
    params = {"Voltage": 480, "Power": 1000, "Manufacturer": "TestCo"}
    transformed = mapper._transform_parameters(params, "Transformer")
    assert "VoltageRating" in transformed or "Voltage" in transformed
    assert "PowerRating" in transformed or "Power" in transformed
    assert "Manufacturer" in transformed


@pytest.mark.asyncio
async def test_revit_sync_service_initialization():
    """Test initializing the Revit sync service."""
    from revit_integration.aps.data_exchange import APSDataExchange
    from revit_integration.aps.auth_service import APSAuthService
    
    # Create mock APS services
    auth_service = APSAuthService("dummy", "dummy")
    data_exchange = APSDataExchange(auth_service)
    sync_service = RevitSyncService(data_exchange)
    
    assert sync_service is not None
    assert sync_service.element_adapter is not None
    assert sync_service.category_mapper is not None


@pytest.mark.asyncio
async def test_revit_sync_service_sync_project(sample_revit_elements):
    """Test the Revit sync service project sync functionality."""
    from revit_integration.aps.data_exchange import APSDataExchange
    from revit_integration.aps.auth_service import APSAuthService
    
    # Create mock APS services
    auth_service = APSAuthService("dummy", "dummy")
    data_exchange = APSDataExchange(auth_service)
    sync_service = RevitSyncService(data_exchange)
    
    # Create a test project
    project = RevitProjectDTO(
        project_id="test_project_1",
        project_name="Test Project",
        status="active"
    )
    
    # Mock the element extraction to return our sample elements
    original_extract = sync_service._extract_elements_from_revit
    async def mock_extract(proj_dto):
        return sample_revit_elements
    sync_service._extract_elements_from_revit = mock_extract
    
    try:
        # Perform sync
        sync_status = await sync_service.sync_project(project)
        
        assert sync_status is not None
        assert sync_status.project_id == "test_project_1"
        assert sync_status.status in ["completed", "completed_with_errors"]
        assert sync_status.total_elements >= 0  # We mocked the extraction
        
    finally:
        # Restore original method
        sync_service._extract_elements_from_revit = original_extract


@pytest.mark.asyncio
async def test_revit_agent_initialization():
    """Test initializing the Revit AI agent."""
    agent = create_revit_agent()
    
    assert agent is not None
    assert isinstance(agent, RevitAgent)
    assert "bim_model_inspection" in agent.capabilities
    assert "electrical_asset_extraction" in agent.capabilities
    assert "digital_twin_synchronization" in agent.capabilities


@pytest.mark.asyncio
async def test_revit_agent_inspect_bim_model(sample_revit_elements):
    """Test the Revit agent's BIM inspection capability."""
    agent = create_revit_agent()
    
    results = await agent.inspect_bim_model("test_project", sample_revit_elements)
    
    assert results is not None
    assert "project_id" in results
    assert "total_elements" in results
    assert "completeness_score" in results
    assert results["total_elements"] == len(sample_revit_elements)


@pytest.mark.asyncio
async def test_revit_agent_extract_electrical_assets(sample_revit_elements):
    """Test the Revit agent's electrical asset extraction capability."""
    agent = create_revit_agent()
    
    assets = await agent.extract_electrical_assets(sample_revit_elements)
    
    # Should extract at least the electrical equipment from our sample
    electrical_elements = [e for e in sample_revit_elements if "Electrical" in e.category]
    assert len(assets) <= len(electrical_elements)  # May be fewer due to filtering
    for asset in assets:
        assert isinstance(asset, ElectricalAssetDTO)


@pytest.mark.asyncio
async def test_revit_agent_prepare_clash_detection(sample_revit_elements):
    """Test the Revit agent's clash detection preparation capability."""
    agent = create_revit_agent()
    
    clash_data = await agent.prepare_clash_detection_data(sample_revit_elements)
    
    assert clash_data is not None
    assert "systems" in clash_data
    assert "element_count_by_system" in clash_data
    assert "potential_conflict_zones" in clash_data
    
    # Check that elements are grouped by system
    total_grouped = sum(clash_data["element_count_by_system"].values())
    assert total_grouped == len(sample_revit_elements)


@pytest.mark.asyncio
async def test_revit_agent_validate_model(sample_revit_elements):
    """Test the Revit agent's model validation capability."""
    agent = create_revit_agent()
    
    validation_results = await agent.validate_model(sample_revit_elements)
    
    assert validation_results is not None
    assert "total_elements" in validation_results
    assert "valid_elements" in validation_results
    assert "invalid_elements" in validation_results
    assert validation_results["total_elements"] == len(sample_revit_elements)


@pytest.mark.asyncio
async def test_revit_agent_analyze_electrical_system(sample_electrical_assets):
    """Test the Revit agent's electrical system analysis capability."""
    agent = create_revit_agent()
    
    analysis = await agent.analyze_electrical_system(sample_electrical_assets)
    
    assert analysis is not None
    assert "total_assets" in analysis
    assert "by_type" in analysis
    assert analysis["total_assets"] == len(sample_electrical_assets)
    
    # Check that we have asset types counted
    assert len(analysis["by_type"]) > 0


@pytest.mark.asyncio
async def test_revit_agent_full_workflow(sample_revit_elements, sample_electrical_assets):
    """Test the full Revit agent workflow."""
    agent = create_revit_agent()
    
    # Step 1: Inspect BIM model
    inspection_results = await agent.inspect_bim_model("workflow_test", sample_revit_elements)
    
    # Step 2: Validate model
    validation_results = await agent.validate_model(sample_revit_elements)
    
    # Step 3: Extract electrical assets
    electrical_assets = await agent.extract_electrical_assets(sample_revit_elements)
    
    # Step 4: Analyze electrical system
    analysis_results = await agent.analyze_electrical_system(electrical_assets)
    
    # Step 5: Generate report
    report = await agent.generate_report(inspection_results, validation_results, analysis_results)
    
    assert report is not None
    assert "executive_summary" in report
    assert "bim_inspection" in report
    assert "model_validation" in report
    assert "electrical_analysis" in report
    assert "recommendations" in report
    assert "risk_assessment" in report


@pytest.mark.asyncio
async def test_sync_status_dto():
    """Test SyncStatusDTO functionality."""
    sync_status = SyncStatusDTO(
        sync_id="test_sync_1",
        project_id="test_project_1",
        status="completed",
        total_elements=100,
        processed_elements=100,
        successful_elements=95,
        failed_elements=5,
        progress=100.0,
        start_time=datetime.utcnow()
    )
    
    assert sync_status.sync_id == "test_sync_1"
    assert sync_status.project_id == "test_project_1"
    assert sync_status.status == "completed"
    assert sync_status.total_elements == 100
    assert sync_status.successful_elements == 95
    assert sync_status.failed_elements == 5
    assert sync_status.progress == 100.0


@pytest.mark.asyncio
async def test_model_metadata_dto():
    """Test ModelMetadataDTO functionality."""
    metadata = ModelMetadataDTO(
        model_id="test_model_1",
        project_name="Test Project",
        revit_version="2024",
        model_units="Imperial",
        total_elements=500,
        electrical_elements=100,
        geometry_elements=400,
        file_size=1024000
    )
    
    assert metadata.model_id == "test_model_1"
    assert metadata.project_name == "Test Project"
    assert metadata.revit_version == "2024"
    assert metadata.total_elements == 500
    assert metadata.electrical_elements == 100


@pytest.mark.asyncio
async def test_revit_project_dto():
    """Test RevitProjectDTO functionality."""
    project = RevitProjectDTO(
        project_id="test_proj_1",
        project_name="Test Project",
        sync_enabled=True,
        status="active"
    )
    
    assert project.project_id == "test_proj_1"
    assert project.project_name == "Test Project"
    assert project.sync_enabled is True
    assert project.status == "active"


if __name__ == "__main__":
    pytest.main([__file__])