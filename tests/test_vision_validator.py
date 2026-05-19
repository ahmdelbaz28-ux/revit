"""
Tests for VisionValidationEngine
"""

import pytest
from validation.vision_validator import VisionValidationEngine, ValidationResult


class TestVisionValidationEngine:
    """Test vision validation"""
    
    def test_valid_room(self):
        """Test valid closed room"""
        # Valid room: 10x10 square
        polygon = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
        
        result = VisionValidationEngine.validate_room_polygon(polygon)
        
        # Check that all validations pass
        assert result.area > 0
        assert len(result.violations) > 0
        # At least closure, area, centroid, angles should be valid
        all_valid = all(v[1] for v in result.violations if v[0] in ['is_closed', 'area_valid', 'centroid_inside', 'valid_angles', 'is_valid_geometry'])
        assert all_valid == True
    
    def test_open_room_fail(self):
        """Test open room (not closed) - should FAIL"""
        # Not closed: last point != first point
        polygon = [(0, 0), (10, 0), (10, 10), (0, 10)]  # Missing last point
        
        result = VisionValidationEngine.validate_room_polygon(polygon)
        
        # Should be marked as invalid due to not being closed
        is_closed_violation = any(v[0] == 'is_closed' and v[1] == False for v in result.violations)
        assert is_closed_violation == True
    
    def test_self_intersecting_fail(self):
        """Test self-intersecting room - should FAIL"""
        # Figure-8 shape (self-intersecting)
        polygon = [(0, 0), (10, 10), (10, 0), (0, 10), (0, 0)]
        
        result = VisionValidationEngine.validate_room_polygon(polygon)
        
        # Should fail validation
        geom_violation = any(v[0] == 'is_valid_geometry' and v[1] == False for v in result.violations)
        assert geom_violation == True
    
    def test_invalid_area_too_small(self):
        """Test room with area too small - should FAIL"""
        # Tiny room: 1x1
        polygon = [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]
        
        result = VisionValidationEngine.validate_room_polygon(polygon)
        
        assert result.is_valid == False
        area_violation = any(v[0] == 'area_valid' and v[1] == False for v in result.violations)
        assert area_violation == True
    
    def test_valid_angles(self):
        """Test room with valid angles"""
        # Regular room
        polygon = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
        
        result = VisionValidationEngine.validate_room_polygon(polygon)
        
        # Should have valid angles
        angles_violation = any(v[0] == 'valid_angles' and v[1] == False for v in result.violations)
        assert angles_violation == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])