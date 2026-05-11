"""
Unit Tests for Domain Models

Tests for core domain entities: Point, Room, Device, Violation
"""

import pytest
from src.domain.models import (
    Point, LineString, Polygon, Room, Device, Obstruction,
    Violation, ViolationSeverity, RoomType, DeviceType
)


class TestPoint:
    """Tests for Point entity"""
    
    def test_point_creation(self):
        """Test basic point creation"""
        p = Point(x=1.0, y=2.0, z=3.0)
        assert p.x == 1.0
        assert p.y == 2.0
        assert p.z == 3.0
    
    def test_point_default_z(self):
        """Test point with default z value"""
        p = Point(x=1.0, y=2.0)
        assert p.z == 0.0
    
    def test_point_to_tuple(self):
        """Test conversion to tuple"""
        p = Point(x=1.0, y=2.0, z=3.0)
        assert p.to_tuple() == (1.0, 2.0, 3.0)
    
    def test_point_distance_to(self):
        """Test distance calculation between points"""
        p1 = Point(x=0.0, y=0.0, z=0.0)
        p2 = Point(x=3.0, y=4.0, z=0.0)
        # Distance should be 5.0 (3-4-5 triangle)
        assert abs(p1.distance_to(p2) - 5.0) < 0.001
    
    def test_point_distance_3d(self):
        """Test 3D distance calculation"""
        p1 = Point(x=0.0, y=0.0, z=0.0)
        p2 = Point(x=1.0, y=2.0, z=2.0)
        # Distance = sqrt(1 + 4 + 4) = 3.0
        assert abs(p1.distance_to(p2) - 3.0) < 0.001


class TestLineString:
    """Tests for LineString entity"""
    
    def test_linestring_creation(self):
        """Test basic line string creation"""
        p1 = Point(x=0.0, y=0.0)
        p2 = Point(x=3.0, y=4.0)
        line = LineString(points=[p1, p2])
        assert len(line.points) == 2
    
    def test_linestring_length(self):
        """Test line string length calculation"""
        p1 = Point(x=0.0, y=0.0)
        p2 = Point(x=3.0, y=4.0)
        line = LineString(points=[p1, p2])
        assert abs(line.length() - 5.0) < 0.001


class TestPolygon:
    """Tests for Polygon entity"""
    
    def test_polygon_creation(self):
        """Test basic polygon creation"""
        points = [
            Point(x=0.0, y=0.0),
            Point(x=10.0, y=0.0),
            Point(x=10.0, y=8.0),
            Point(x=0.0, y=8.0)
        ]
        poly = Polygon(exterior=points)
        assert len(poly.exterior) == 4
    
    def test_polygon_area_rectangle(self):
        """Test area calculation for rectangle"""
        points = [
            Point(x=0.0, y=0.0),
            Point(x=10.0, y=0.0),
            Point(x=10.0, y=8.0),
            Point(x=0.0, y=8.0)
        ]
        poly = Polygon(exterior=points)
        assert abs(poly.area() - 80.0) < 0.001
    
    def test_polygon_with_holes(self):
        """Test polygon with holes"""
        exterior = [
            Point(x=0.0, y=0.0),
            Point(x=10.0, y=0.0),
            Point(x=10.0, y=10.0),
            Point(x=0.0, y=10.0)
        ]
        hole = [
            Point(x=2.0, y=2.0),
            Point(x=4.0, y=2.0),
            Point(x=4.0, y=4.0),
            Point(x=2.0, y=4.0)
        ]
        poly = Polygon(exterior=exterior, holes=[hole])
        assert len(poly.holes) == 1


class TestRoom:
    """Tests for Room entity"""
    
    def test_room_creation_basic(self):
        """Test basic room creation"""
        room = Room(name="Office 101", room_type=RoomType.OFFICE)
        assert room.name == "Office 101"
        assert room.room_type == RoomType.OFFICE
        assert room.height == 3.0  # Default
    
    def test_room_area_from_dimensions(self):
        """Test area calculation from length and width"""
        room = Room(length=10.0, width=8.0)
        assert room.area == 80.0
    
    def test_room_area_from_polygon(self):
        """Test area calculation from polygon"""
        points = [
            Point(x=0.0, y=0.0),
            Point(x=10.0, y=0.0),
            Point(x=10.0, y=8.0),
            Point(x=0.0, y=8.0)
        ]
        polygon = Polygon(exterior=points)
        room = Room(polygon=polygon)
        assert abs(room.area - 80.0) < 0.001
    
    def test_room_get_walls(self):
        """Test wall extraction from room"""
        points = [
            Point(x=0.0, y=0.0),
            Point(x=10.0, y=0.0),
            Point(x=10.0, y=8.0),
            Point(x=0.0, y=8.0)
        ]
        polygon = Polygon(exterior=points)
        room = Room(polygon=polygon)
        walls = room.get_walls()
        assert len(walls) == 4
    
    def test_room_get_centroid(self):
        """Test centroid calculation"""
        points = [
            Point(x=0.0, y=0.0),
            Point(x=10.0, y=0.0),
            Point(x=10.0, y=8.0),
            Point(x=0.0, y=8.0)
        ]
        polygon = Polygon(exterior=points)
        room = Room(polygon=polygon)
        centroid = room.get_centroid()
        assert centroid is not None
        assert abs(centroid.x - 5.0) < 0.001
        assert abs(centroid.y - 4.0) < 0.001


class TestDevice:
    """Tests for Device entity"""
    
    def test_device_creation(self):
        """Test basic device creation"""
        device = Device(device_type=DeviceType.SMOKE_DETECTOR)
        assert device.device_type == DeviceType.SMOKE_DETECTOR
        assert device.coverage_radius == 7.5  # Default
    
    def test_device_position_from_xy(self):
        """Test position initialization from x,y coordinates"""
        device = Device(x=5.0, y=10.0, z=2.5)
        assert device.position is not None
        assert device.position.x == 5.0
        assert device.position.y == 10.0
        assert device.position.z == 2.5
    
    def test_device_distance_to_wall(self):
        """Test wall distance calculation"""
        points = [
            Point(x=0.0, y=0.0),
            Point(x=10.0, y=0.0),
            Point(x=10.0, y=8.0),
            Point(x=0.0, y=8.0)
        ]
        polygon = Polygon(exterior=points)
        room = Room(polygon=polygon)
        
        # Device in center should be 4.0m from nearest wall
        device = Device(x=5.0, y=4.0)
        distance = device.distance_to_wall(room)
        assert abs(distance - 4.0) < 0.001


class TestViolation:
    """Tests for Violation entity"""
    
    def test_violation_creation(self):
        """Test basic violation creation"""
        violation = Violation(
            violation_code="TEST_CODE",
            standard_name="Test Standard",
            severity=ViolationSeverity.MAJOR,
            description_template="Test violation: {param}",
            params={'param': 'value'}
        )
        assert violation.violation_code == "TEST_CODE"
        assert violation.severity == ViolationSeverity.MAJOR
    
    def test_violation_message_generation(self):
        """Test message generation from template"""
        violation = Violation(
            violation_code="TEST_CODE",
            standard_name="Test Standard",
            description_template="Value is {value}, expected {expected}",
            params={'value': 10, 'expected': 20}
        )
        assert violation.message == "Value is 10, expected 20"
    
    def test_violation_to_dict(self):
        """Test conversion to dictionary"""
        violation = Violation(
            violation_code="TEST_CODE",
            standard_name="Test Standard",
            severity=ViolationSeverity.CRITICAL,
            params={'key': 'value'}
        )
        d = violation.to_dict()
        assert d['violation_code'] == "TEST_CODE"
        assert d['severity'] == "Critical"
        assert 'message' in d


class TestValidationHelpers:
    """Tests for validation helper functions"""
    
    def test_validate_room_no_name(self):
        """Test room validation catches missing name"""
        from src.domain.models import validate_room
        room = Room()  # No name
        violations = validate_room(room)
        assert len(violations) > 0
        assert any(v.violation_code == "ROOM_NO_NAME" for v in violations)
    
    def test_validate_room_invalid_area(self):
        """Test room validation catches invalid area"""
        from src.domain.models import validate_room
        room = Room(area=-5.0)
        violations = validate_room(room)
        assert any(v.violation_code == "ROOM_INVALID_AREA" for v in violations)
    
    def test_validate_device_no_position(self):
        """Test device validation catches missing position"""
        from src.domain.models import validate_device
        device = Device()  # No position
        violations = validate_device(device)
        assert any(v.violation_code == "DEVICE_NO_POSITION" for v in violations)
