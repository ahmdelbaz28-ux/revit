"""
Tests for Universal Data Model
"""

import pytest
from core.models import (
    UniversalElement, ElementType, Point3D, Geometry, 
    SemanticProperties, ChangeSource
)
from core.database import UniversalDataModel


class TestCreateWallElement:
    """Test creating a wall element"""
    
    def test_create_wall_element(self):
        """Create UniversalElement as WALL with 4 points, closed polyline, height 3.5m"""
        # Create 4 corner points
        points = [
            Point3D(0, 0, 0),
            Point3D(10, 0, 0),
            Point3D(10, 3.5, 0),
            Point3D(0, 3.5, 0)
        ]
        
        # Create geometry
        geometry = Geometry(points=points, polyline_closed=True)
        geometry.calculate_area()
        geometry.calculate_perimeter()
        
        # Create properties
        properties = SemanticProperties(
            element_type=ElementType.WALL,
            name="Test Wall",
            height=3.5,
            layer="FA_WALLS"
        )
        
        # Create element
        element = UniversalElement(
            properties=properties,
            geometry=geometry,
            source_file="test.dwg",
            last_modified_by=ChangeSource.AUTOCAD.value
        )
        
        # Assertions
        assert element.properties.element_type == ElementType.WALL
        assert element.properties.height == 3.5
        assert len(element.geometry.points) == 4
        assert element.geometry.polyline_closed == True
        assert element.geometry.area > 0
        assert element.geometry.perimeter > 0


class TestSemanticValidation:
    """Test semantic consistency validation"""
    
    def test_validate_semantic_consistency_failure(self):
        """Create wall without height - should fail validation"""
        points = [
            Point3D(0, 0, 0),
            Point3D(10, 0, 0),
            Point3D(10, 3.5, 0),
            Point3D(0, 3.5, 0)
        ]
        
        geometry = Geometry(points=points, polyline_closed=True)
        
        # Create properties WITHOUT height
        properties = SemanticProperties(
            element_type=ElementType.WALL,
            name="Test Wall",
            height=None,  # Missing height!
            layer="FA_WALLS"
        )
        
        element = UniversalElement(
            properties=properties,
            geometry=geometry,
            source_file="test.dwg"
        )
        
        # Validate
        is_valid, errors = element.validate_semantic_consistency()
        
        # Should fail
        assert is_valid == False
        assert len(errors) > 0
        # Check error message mentions height
        error_msg = ' '.join(errors).lower()
        assert 'height' in error_msg


class TestAddElement:
    """Test adding elements to model"""
    
    def test_add_element_to_model(self):
        """Add ROOM element to UniversalDataModel"""
        import tempfile
        import os
        
        # Create temp db
        temp_db = tempfile.mktemp(suffix='.db')
        
        try:
            model = UniversalDataModel(temp_db)
            
            # Create room element
            points = [
                Point3D(0, 0, 0),
                Point3D(10, 0, 0),
                Point3D(10, 10, 0),
                Point3D(0, 10, 0)
            ]
            
            geometry = Geometry(points=points, polyline_closed=True)
            geometry.calculate_area()
            geometry.calculate_perimeter()
            
            properties = SemanticProperties(
                element_type=ElementType.ROOM,
                name="Living Room",
                height=3.0,
                layer="FA_ROOMS"
            )
            
            element = UniversalElement(
                properties=properties,
                geometry=geometry,
                source_file="test.rvt",
                last_modified_by=ChangeSource.REVIT.value
            )
            
            # Add to model
            result = model.add_element(element)
            assert result == True
            
            # Check count
            assert len(model.elements) == 1
            
            # Retrieve by element_id
            retrieved = model.elements.get(element.element_id)
            assert retrieved is not None
            assert retrieved.element_id == element.element_id
            
            # Check not deleted
            assert retrieved.is_deleted == False
        
        finally:
            if os.path.exists(temp_db):
                os.remove(temp_db)


class TestUpdateElement:
    """Test updating elements"""
    
    def test_update_element(self):
        """Update wall height from 3.5 to 4.0"""
        import tempfile
        import os
        
        temp_db = tempfile.mktemp(suffix='.db')
        
        try:
            model = UniversalDataModel(temp_db)
            
            # Create wall
            points = [
                Point3D(0, 0, 0),
                Point3D(10, 0, 0),
                Point3D(10, 3.5, 0),
                Point3D(0, 3.5, 0)
            ]
            
            geometry = Geometry(points=points, polyline_closed=True)
            
            properties = SemanticProperties(
                element_type=ElementType.WALL,
                name="Test Wall",
                height=3.5,
                layer="FA_WALLS"
            )
            
            element = UniversalElement(
                properties=properties,
                geometry=geometry,
                source_file="test.dwg",
                last_modified_by=ChangeSource.AUTOCAD.value
            )
            
            model.add_element(element)
            element_id = element.element_id
            
            # Update height
            updates = {'properties': {'height': 4.0}}
            result = model.update_element(
                element_id,
                updates,
                source=ChangeSource.REVIT
            )
            assert result == True
            
            # Check height changed
            updated_element = model.elements[element_id]
            assert updated_element.properties.height == 4.0
            
            # Check version
            assert updated_element.version == 1
            
            # Check pending changes
            assert element_id in model.pending_changes['autocad']
        
        finally:
            if os.path.exists(temp_db):
                os.remove(temp_db)


class TestSoftDelete:
    """Test soft delete"""
    
    def test_soft_delete_element(self):
        """Soft delete an element"""
        import tempfile
        import os
        
        temp_db = tempfile.mktemp(suffix='.db')
        
        try:
            model = UniversalDataModel(temp_db)
            
            # Create room
            points = [Point3D(0, 0, 0), Point3D(10, 0, 0), Point3D(10, 10, 0), Point3D(0, 10, 0)]
            geometry = Geometry(points=points, polyline_closed=True)
            
            properties = SemanticProperties(
                element_type=ElementType.ROOM,
                name="Test Room",
                height=3.0
            )
            
            element = UniversalElement(
                properties=properties,
                geometry=geometry,
                source_file="test.rvt",
                last_modified_by=ChangeSource.REVIT.value
            )
            
            model.add_element(element)
            element_id = element.element_id
            
            # Soft delete
            result = model.delete_element(element_id, source=ChangeSource.REVIT)
            assert result == True
            
            # Check is_deleted
            deleted_element = model.elements[element_id]
            assert deleted_element.is_deleted == True
            
            # Element still in model
            assert element_id in model.elements
            
            # In pending changes
            assert element_id in model.pending_changes['autocad']
        
        finally:
            if os.path.exists(temp_db):
                os.remove(temp_db)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])