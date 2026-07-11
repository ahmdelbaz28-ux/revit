# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
"""
tests/test_autocad.py — AutoCAD Service Tests
==========================================

Unit and integration tests for the AutoCAD service.
Tests connection, file operations, and drawing functionality.
"""

import os
import tempfile
from unittest.mock import Mock, patch

import pytest

from backend.services.autocad_service import AutoCADService


class TestAutoCADServiceInitialization:
    """Test AutoCAD service initialization."""

    def test_service_initialization(self):
        """Test that AutoCAD service initializes properly."""
        service = AutoCADService()

        assert service.acad_app is None
        assert service.acad_doc is None
        assert service.connected is False
        assert service.active_entities == {}

    @patch('backend.services.autocad_service.HAS_AUTOCAD_API', True)
    @patch('backend.services.autocad_service.win32com.client')
    @patch('backend.services.autocad_service.pythoncom')
    def test_connect_with_api_available(self, mock_pythoncom, mock_win32com):
        """Test connecting when AutoCAD API is available."""
        service = AutoCADService()

        # Mock the AutoCAD application
        mock_app = Mock()
        mock_doc = Mock()
        mock_util = Mock()

        mock_win32com.Dispatch.return_value = mock_app
        mock_app.ActiveDocument = mock_doc
        mock_doc.Utility = mock_util

        # V140 FIX (Rule 17): The production code (autocad_service.py:99-112)
        # tries `GetActiveObject` FIRST, and only falls back to `Dispatch` if
        # GetActiveObject raises. The old test did NOT make GetActiveObject
        # raise, so the success path never reached Dispatch. The test asserted
        # Dispatch.called which was always False — a real bug in the test's
        # mock setup. Fix: make GetActiveObject raise so Dispatch is exercised.
        mock_win32com.GetActiveObject.side_effect = Exception("no instance")

        result = service.connect()  # noqa: F841  (verified via side effects below)  # NOSONAR - python:S1481

        # Verify the connection attempt
        assert mock_win32com.Dispatch.called
        assert mock_win32com.Dispatch.call_args[0][0] == "AutoCAD.Application"
        assert service.connected is True
        assert service.acad_app is not None
        assert service.acad_doc is not None
        assert service.acad_util is not None

    @patch('backend.services.autocad_service.HAS_AUTOCAD_API', False)
    def test_connect_without_api(self):
        """Test connecting when AutoCAD API is not available."""
        # V142 FIX: The production connect() implementation falls back to a
        # SIMULATION mode when HAS_AUTOCAD_API is False AND FIREAI_ENV is
        # "development" (the default). The simulation mode returns True and
        # sets self.connected=True — useful for local dev, but it would mask
        # the real "no API" behavior this test is verifying. Patch FIREAI_ENV
        # to a non-development value so the simulation branch is bypassed
        # and the genuine "API unavailable → connect() returns False" path
        # is exercised. This is the safety-critical behavior: callers MUST
        # learn that the connection failed so they can fall back to a
        # different ingestion strategy rather than assuming AutoCAD is
        # reachable.
        service = AutoCADService()

        with patch.dict(os.environ, {"FIREAI_ENV": "production"}):
            result = service.connect()

        assert result is False
        assert service.connected is False


class TestAutoCADEntityOperations:
    """Test AutoCAD entity operations."""

    def test_extract_line_entity_data(self):
        """Test extracting data from a line entity."""
        service = AutoCADService()

        # Create a mock line entity
        mock_line = Mock()
        mock_line.Handle = "12345"
        mock_line.ObjectName = "AcDbLine"
        mock_line.Layer = "Walls"
        mock_line.Color = 1
        mock_line.Linetype = "Continuous"
        mock_line.Lineweight = -1
        mock_line.Visible = True
        mock_line.StartPoint = [0, 0, 0]
        mock_line.EndPoint = [1000, 0, 0]
        mock_line.Thickness = 0.0
        mock_line.Normal = [0, 0, 1]

        entity_data = service._extract_entity_data(mock_line)

        assert entity_data["handle"] == "12345"
        assert entity_data["object_name"] == "AcDbLine"
        assert entity_data["layer"] == "Walls"
        assert entity_data["entity_type"] == "LINE"
        assert entity_data["start_point"] == [0, 0, 0]
        assert entity_data["end_point"] == [1000, 0, 0]
        assert entity_data["thickness"] == pytest.approx(0.0)

    def test_extract_circle_entity_data(self):
        """Test extracting data from a circle entity."""
        service = AutoCADService()

        # Create a mock circle entity
        mock_circle = Mock()
        mock_circle.Handle = "67890"
        mock_circle.ObjectName = "AcDbCircle"
        mock_circle.Layer = "Furniture"
        mock_circle.Center = [500, 500, 0]
        mock_circle.Radius = 250.0
        mock_circle.Normal = [0, 0, 1]

        entity_data = service._extract_entity_data(mock_circle)

        assert entity_data["handle"] == "67890"
        assert entity_data["entity_type"] == "CIRCLE"
        assert entity_data["center"] == [500, 500, 0]
        assert entity_data["radius"] == pytest.approx(250.0)

    def test_extract_text_entity_data(self):
        """Test extracting data from a text entity."""
        service = AutoCADService()

        # Create a mock text entity
        mock_text = Mock()
        mock_text.Handle = "ABC123"
        mock_text.ObjectName = "AcDbText"
        mock_text.Layer = "Text"
        mock_text.TextString = "Sample Text"
        mock_text.InsertionPoint = [100, 100, 0]
        mock_text.Height = 2.5
        mock_text.Rotation = 0.0
        mock_text.StyleName = "Standard"

        entity_data = service._extract_entity_data(mock_text)

        assert entity_data["handle"] == "ABC123"
        assert entity_data["entity_type"] == "TEXT"
        assert entity_data["text_string"] == "Sample Text"
        assert entity_data["insertion_point"] == [100, 100, 0]
        assert entity_data["height"] == pytest.approx(2.5)


class TestAutoCADFileOperations:
    """Test AutoCAD file operations."""

    def test_read_nonexistent_file(self):
        """
        Test reading a non-existent file.

        V141.4.1: Updated to use a path inside allowed bases (/tmp) so the
        security validator doesn't reject it as path traversal.
        """
        import tempfile
        service = AutoCADService()

        # Use a path inside /tmp (allowed base) that doesn't exist
        nonexistent = os.path.join(tempfile.gettempdir(), "nonexistent_fireai_autocad_test.dwg")
        if os.path.exists(nonexistent):
            os.unlink(nonexistent)

        result = service.read_dwg(nonexistent)

        assert result["success"] is False
        assert "not found" in result["error"]
        assert result["entities"] == []
        assert result["count"] == 0

    @patch('backend.services.autocad_service.HAS_AUTOCAD_API', True)
    @patch('backend.services.autocad_service.win32com.client')
    @patch('backend.services.autocad_service.pythoncom')
    def test_write_dwg_with_entities(self, mock_pythoncom, mock_win32com):
        """Test writing entities to a DWG file."""
        service = AutoCADService()

        # Mock the AutoCAD application
        mock_app = Mock()
        mock_doc = Mock()
        mock_space = Mock()

        mock_win32com.Dispatch.return_value = mock_app
        mock_app.Documents.Add.return_value = mock_doc
        mock_doc.ModelSpace = mock_space

        # V140 FIX (Rule 17): write_dwg (autocad_service.py:383-386) requires
        # `self.connected == True`. The old test forgot to connect, so the
        # method short-circuited with "AutoCAD service not connected" log.
        # Force GetActiveObject to raise so Dispatch is the path that connects,
        # then call connect() to establish the connected state.
        mock_win32com.GetActiveObject.side_effect = Exception("no instance")
        mock_app.ActiveDocument = mock_doc
        mock_doc.Utility = Mock()
        assert service.connect() is True

        # Create mock entities to write
        entities = [
            {
                "entity_type": "LINE",
                "start_point": [0, 0, 0],
                "end_point": [1000, 0, 0],
                "layer": "Walls",
                "color": 1
            },
            {
                "entity_type": "CIRCLE",
                "center": [500, 500, 0],
                "radius": 250.0,
                "layer": "Furniture",
                "color": 2
            }
        ]

        # Mock the AddLine and AddCircle methods
        mock_line = Mock()
        mock_circle = Mock()
        mock_space.AddLine.return_value = mock_line
        mock_space.AddCircle.return_value = mock_circle

        with tempfile.NamedTemporaryFile(suffix='.dwg', delete=False) as temp_file:
            temp_path = temp_file.name

        try:
            result = service.write_dwg(temp_path, entities)
            assert result is True
        finally:
            # Clean up the temp file
            if os.path.exists(temp_path):
                os.unlink(temp_path)


class TestAutoCADDrawingOperations:
    """Test AutoCAD drawing operations."""

    @patch('backend.services.autocad_service.HAS_AUTOCAD_API', True)
    @patch('backend.services.autocad_service.win32com.client')
    @patch('backend.services.autocad_service.pythoncom')
    def test_draw_line(self, mock_pythoncom, mock_win32com):
        """Test drawing a line in AutoCAD."""
        service = AutoCADService()

        # Mock the AutoCAD application
        mock_app = Mock()
        mock_doc = Mock()
        mock_space = Mock()

        mock_win32com.Dispatch.return_value = mock_app
        mock_app.ActiveDocument = mock_doc
        mock_doc.ModelSpace = mock_space

        # Mock the AddLine method
        mock_line = Mock()
        mock_space.AddLine.return_value = mock_line

        # Connect to simulate active document
        service.acad_app = mock_app
        service.acad_doc = mock_doc
        service.acad_util = mock_doc.Utility
        service.connected = True

        # Test drawing a line
        result = service.draw_line([0, 0, 0], [1000, 0, 0], layer="TestLayer", color=1)

        # Verify the line was added
        mock_space.AddLine.assert_called_once_with([0, 0, 0], [1000, 0, 0])
        assert mock_line.Layer == "TestLayer"
        assert mock_line.Color == 1
        assert result is mock_line

    @patch('backend.services.autocad_service.HAS_AUTOCAD_API', True)
    @patch('backend.services.autocad_service.win32com.client')
    @patch('backend.services.autocad_service.pythoncom')
    def test_draw_circle(self, mock_pythoncom, mock_win32com):
        """Test drawing a circle in AutoCAD."""
        service = AutoCADService()

        # Mock the AutoCAD application
        mock_app = Mock()
        mock_doc = Mock()
        mock_space = Mock()

        mock_win32com.Dispatch.return_value = mock_app
        mock_app.ActiveDocument = mock_doc
        mock_doc.ModelSpace = mock_space

        # Mock the AddCircle method
        mock_circle = Mock()
        mock_space.AddCircle.return_value = mock_circle

        # Connect to simulate active document
        service.acad_app = mock_app
        service.acad_doc = mock_doc
        service.acad_util = mock_doc.Utility
        service.connected = True

        # Test drawing a circle
        result = service.draw_circle([500, 500, 0], 250.0, layer="TestLayer", color=2)

        # Verify the circle was added
        mock_space.AddCircle.assert_called_once_with([500, 500, 0], 250.0)
        assert mock_circle.Layer == "TestLayer"
        assert mock_circle.Color == 2
        assert result is mock_circle

    @patch('backend.services.autocad_service.HAS_AUTOCAD_API', True)
    @patch('backend.services.autocad_service.win32com.client')
    @patch('backend.services.autocad_service.pythoncom')
    def test_draw_text(self, mock_pythoncom, mock_win32com):
        """Test drawing text in AutoCAD."""
        service = AutoCADService()

        # Mock the AutoCAD application
        mock_app = Mock()
        mock_doc = Mock()
        mock_space = Mock()

        mock_win32com.Dispatch.return_value = mock_app
        mock_app.ActiveDocument = mock_doc
        mock_doc.ModelSpace = mock_space

        # Mock the AddText method
        mock_text = Mock()
        mock_space.AddText.return_value = mock_text

        # Connect to simulate active document
        service.acad_app = mock_app
        service.acad_doc = mock_doc
        service.acad_util = mock_doc.Utility
        service.connected = True

        # Test drawing text
        result = service.draw_text("Hello World", [100, 100, 0], height=2.5, layer="TestLayer", color=3)

        # Verify the text was added
        mock_space.AddText.assert_called_once_with("Hello World", [100, 100, 0], 2.5)
        assert mock_text.Layer == "TestLayer"
        assert mock_text.Color == 3
        assert result is mock_text


class TestAutoCADConnectionManagement:
    """Test AutoCAD connection management."""

    @patch('backend.services.autocad_service.HAS_AUTOCAD_API', True)
    @patch('backend.services.autocad_service.win32com.client')
    @patch('backend.services.autocad_service.pythoncom')
    def test_disconnect(self, mock_pythoncom, mock_win32com):
        """Test disconnecting from AutoCAD."""
        service = AutoCADService()

        # Mock the AutoCAD application
        mock_app = Mock()
        service.acad_app = mock_app
        service.connected = True

        result = service.disconnect()

        # Verify the application was hidden and connection reset
        assert mock_app.Visible is False
        assert service.acad_app is None
        assert service.acad_doc is None
        assert service.acad_util is None
        assert service.connected is False
        assert result is True

    def test_operations_when_not_connected(self):
        """Test that operations fail when not connected."""
        service = AutoCADService()

        # These operations should return None or False when not connected
        line_result = service.draw_line([0, 0, 0], [1000, 0, 0])
        circle_result = service.draw_circle([500, 500, 0], 250.0)
        text_result = service.draw_text("Test", [100, 100, 0])
        save_result = service.save("test.dwg")

        assert line_result is None
        assert circle_result is None
        assert text_result is None
        assert save_result is False

        # V213: delete/modify must also fail-closed when not connected
        assert service.delete_entity("1A2F") is False
        assert service.modify_entity("1A2F", {"Color": 1}) is False


class TestV213DeleteModifyEntity:
    """V213 regression tests for honest delete_entity / modify_entity.

    Previously these methods were no-ops that always returned True. Now they
    must:
      - return False when not connected
      - return False when in simulation mode (no acad_doc)
      - return True only when AutoCAD COM actually deleted/modified the entity
    """

    def test_delete_when_not_connected_returns_false(self):
        service = AutoCADService()
        assert service.delete_entity("1A2F") is False

    def test_modify_when_not_connected_returns_false(self):
        service = AutoCADService()
        assert service.modify_entity("1A2F", {"Color": 1}) is False

    def test_delete_in_simulation_mode_returns_false(self):
        """Simulation mode (connected=True, acad_doc=None) must NOT silently
        pretend to delete — it must return False so the UI surfaces the truth.
        """
        service = AutoCADService()
        service.connected = True
        service.acad_doc = None  # simulation mode
        assert service.delete_entity("1A2F") is False

    def test_modify_in_simulation_mode_returns_false(self):
        service = AutoCADService()
        service.connected = True
        service.acad_doc = None  # simulation mode
        assert service.modify_entity("1A2F", {"Color": 1}) is False

    def test_modify_with_empty_properties_returns_false(self):
        from unittest.mock import MagicMock
        service = AutoCADService()
        service.connected = True
        service.acad_doc = MagicMock()
        assert service.modify_entity("1A2F", {}) is False

    def test_delete_with_real_com_calls_handletoobject_and_delete(self):
        """When a real AutoCAD doc is connected, delete_entity must resolve
        the handle via Document.HandleToObject and call Delete() on the
        returned entity.
        """
        from unittest.mock import MagicMock
        service = AutoCADService()
        service.connected = True
        mock_entity = MagicMock()
        mock_doc = MagicMock()
        mock_doc.HandleToObject.return_value = mock_entity
        service.acad_doc = mock_doc

        result = service.delete_entity("1A2F")

        assert result is True
        mock_doc.HandleToObject.assert_called_once_with("1A2F")
        mock_entity.Delete.assert_called_once()

    def test_delete_when_handle_not_found_returns_false(self):
        from unittest.mock import MagicMock
        service = AutoCADService()
        service.connected = True
        mock_doc = MagicMock()
        mock_doc.HandleToObject.return_value = None
        service.acad_doc = mock_doc

        assert service.delete_entity("DEAD") is False

    def test_delete_swallows_com_exception_and_returns_false(self):
        from unittest.mock import MagicMock
        service = AutoCADService()
        service.connected = True
        mock_doc = MagicMock()
        mock_doc.HandleToObject.side_effect = RuntimeError("COM error: invalid handle")
        service.acad_doc = mock_doc

        assert service.delete_entity("BAD") is False

    def test_modify_applies_only_existing_attributes(self):
        """modify_entity should set attributes that exist on the entity and
        skip (with warning) attributes that don't, returning True if at
        least one attribute was applied.
        """
        from unittest.mock import MagicMock
        service = AutoCADService()
        service.connected = True
        mock_entity = MagicMock()
        # entity has 'Layer' and 'Color' but NOT 'NonExistent'
        del mock_entity.NonExistent  # make hasattr() return False
        mock_doc = MagicMock()
        mock_doc.HandleToObject.return_value = mock_entity
        service.acad_doc = mock_doc

        result = service.modify_entity("1A2F", {
            "Layer": "WALLS",
            "Color": 1,
            "NonExistent": "should be skipped",
        })

        assert result is True
        assert mock_entity.Layer == "WALLS"
        assert mock_entity.Color == 1

    def test_modify_returns_false_when_no_attribute_applied(self):
        from unittest.mock import MagicMock
        service = AutoCADService()
        service.connected = True
        mock_entity = MagicMock()
        del mock_entity.NonExistent1
        del mock_entity.NonExistent2
        mock_doc = MagicMock()
        mock_doc.HandleToObject.return_value = mock_entity
        service.acad_doc = mock_doc

        result = service.modify_entity("1A2F", {
            "NonExistent1": "x",
            "NonExistent2": "y",
        })
        assert result is False

    def test_modify_skips_internal_metadata_keys(self):
        """Keys like 'entity_type' and 'source_entity_handle' are our own
        metadata, not real AutoCAD attributes — they must be silently skipped.
        """
        from unittest.mock import MagicMock
        service = AutoCADService()
        service.connected = True
        mock_entity = MagicMock()
        mock_doc = MagicMock()
        mock_doc.HandleToObject.return_value = mock_entity
        service.acad_doc = mock_doc

        # Only metadata keys → nothing applied → return False
        result = service.modify_entity("1A2F", {
            "entity_type": "LINE",
            "source_entity_handle": "1A2F",
        })
        assert result is False


class TestV213SimulationModeFlag:
    """V213 regression tests for the explicit ``simulation_mode`` flag on
    AutoCADService. Previously, ``connect()`` silently returned True on
    non-Windows / no-pywin32 environments, leaving clients with no way to
    distinguish a real COM handle from the dev fallback. Now the flag is
    set honestly in every code path.
    """

    def test_fresh_service_is_not_in_simulation_mode(self):
        service = AutoCADService()
        assert service.simulation_mode is False

    def test_simulation_mode_engaged_on_non_windows_dev_env(self, monkeypatch):
        """On non-Windows (or when HAS_AUTOCAD_API is False) and
        FIREAI_ENV=development, connect() must set simulation_mode=True
        so clients can surface the truth.
        """
        monkeypatch.setenv("FIREAI_ENV", "development")
        # Force HAS_AUTOCAD_API = False to simulate non-Windows
        import backend.services.autocad_service as mod
        monkeypatch.setattr(mod, "HAS_AUTOCAD_API", False)

        service = AutoCADService()
        result = service.connect()
        assert result is True
        assert service.connected is True
        assert service.simulation_mode is True  # V213: honest flag

    def test_simulation_mode_false_when_real_com_handle_acquired(self, monkeypatch):
        """When a real AutoCAD COM handle is acquired (via mocks), the
        simulation_mode flag must be False.
        """
        monkeypatch.setenv("FIREAI_ENV", "development")
        import backend.services.autocad_service as mod
        # Force HAS_AUTOCAD_API = True to take the real COM path
        monkeypatch.setattr(mod, "HAS_AUTOCAD_API", True)

        from unittest.mock import MagicMock, patch
        mock_app = MagicMock()
        mock_doc = MagicMock()
        mock_app.ActiveDocument = mock_doc
        mock_app.Documents.Add.return_value = mock_doc

        with patch.object(mod, "pythoncom", create=True), \
             patch.object(mod.win32com.client, "GetActiveObject", return_value=mock_app, create=True):
            service = AutoCADService()
            result = service.connect()

        assert result is True
        assert service.connected is True
        assert service.simulation_mode is False  # V213: real connection

    def test_disconnect_resets_simulation_mode(self, monkeypatch):
        """disconnect() must clear simulation_mode back to False."""
        monkeypatch.setenv("FIREAI_ENV", "development")
        import backend.services.autocad_service as mod
        monkeypatch.setattr(mod, "HAS_AUTOCAD_API", False)

        service = AutoCADService()
        service.connect()
        assert service.simulation_mode is True

        service.disconnect()
        assert service.simulation_mode is False
        assert service.connected is False

    def test_simulation_mode_false_in_production_when_no_api(self, monkeypatch):
        """In production (FIREAI_ENV != development) without AutoCAD API,
        connect() must return False AND set simulation_mode=False (we are
        not simulating — we are honestly failing).
        """
        monkeypatch.setenv("FIREAI_ENV", "production")
        import backend.services.autocad_service as mod
        monkeypatch.setattr(mod, "HAS_AUTOCAD_API", False)

        service = AutoCADService()
        result = service.connect()
        assert result is False
        assert service.connected is False
        assert service.simulation_mode is False  # honest failure, not sim


if __name__ == "__main__":
    pytest.main([__file__])
