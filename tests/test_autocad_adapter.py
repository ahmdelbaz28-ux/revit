"""
tests/test_autocad_adapter.py
AutoCAD Adapter Tests - TRL 7
"""

import pytest
from unittest.mock import Mock
from core.database import UniversalDataModel
from core.sync_engine import LiveSyncEngine
from adapters.autocad_adapter import AutoCADAdapter


@pytest.fixture
def setup_adapter():
    db = UniversalDataModel(":memory:")
    sync = LiveSyncEngine(None, None)
    adapter = AutoCADAdapter(db, sync, use_mock=True)
    return adapter


def test_start_monitoring_mock(setup_adapter):
    """Test connection and monitoring start in Mock mode"""
    adapter = setup_adapter
    assert adapter.start_monitoring() == True
    assert adapter._is_monitoring == True


def test_import_drawing_mock(setup_adapter):
    """Test importing elements from mock drawing"""
    adapter = setup_adapter
    adapter.start_monitoring()
    elements = adapter.import_current_drawing()
    assert len(elements) > 0


def test_entity_lifecycle_mock(setup_adapter):
    """Test Add -> Modify -> Delete cycle"""
    adapter = setup_adapter
    adapter.start_monitoring()
    
    mock_entity = {"id": "test_1", "type": "LINE"}
    assert adapter.on_entity_added(mock_entity) == True
    
    assert adapter.on_entity_modified("test_1", {"length": 10}) == True
    
    assert adapter.on_entity_deleted("test_1") == True