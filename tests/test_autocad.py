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

        result = service.connect()  # noqa: F841  (verified via side effects below)

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
        service = AutoCADService()

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
        assert entity_data["thickness"] == 0.0

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
        assert entity_data["radius"] == 250.0

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
        assert entity_data["height"] == 2.5


class TestAutoCADFileOperations:
    """Test AutoCAD file operations."""

    def test_read_nonexistent_file(self):
        """Test reading a non-existent file.

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


if __name__ == "__main__":
    pytest.main([__file__])
