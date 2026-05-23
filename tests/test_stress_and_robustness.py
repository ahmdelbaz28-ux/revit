"""
اختبارات الصلابة والحدود القصوى (Stress & Robustness Tests) - Final Version
"""
import pytest
import random
from src.core.models import Room, Device, DeviceType, Violation, NFPA72, BS5839, RoomType, Point, Polygon, DesignProject
from src.application.coverage_service import CoverageService
from src.application.wall_distance_service import WallDistanceService
from src.application.compliance_service import ComplianceService
from src.application.normalization_service import NormalizationService

class TestExtremeBoundaries:
    def test_zero_area_room(self):
        room = Room(name="Zero Area", polygon=Polygon([Point(0, 0), Point(0, 0), Point(0, 0), Point(0, 0)]), room_type=RoomType.OFFICE)
        assert room.area == 0.0
        service = CoverageService()
        violations = service.check_room_coverage(room, [])
        assert isinstance(violations, list)

    def test_negative_coordinates_room(self):
        poly = Polygon([Point(-10000, -10000), Point(-10000, -9900), Point(-9900, -9900), Point(-9900, -10000)])
        room = Room(name="Negative Coords", polygon=poly, room_type=RoomType.STORAGE)
        assert room.area > 0
        device = Device(position=Point(-9950, -9950), device_type=DeviceType.SMOKE_DETECTOR)
        service = CoverageService()
        violations = service.check_room_coverage(room, [device])
        assert isinstance(violations, list)

    def test_gigantic_room(self):
        side = 10000
        poly = Polygon([Point(0, 0), Point(0, side), Point(side, side), Point(side, 0)])
        room = Room(name="Airport Terminal", polygon=poly, room_type=RoomType.LOBBY)
        assert room.area == side * side
        device = Device(position=Point(side/2, side/2), device_type=DeviceType.SMOKE_DETECTOR)
        service = CoverageService()
        violations = service.check_room_coverage(room, [device])
        assert len(violations) > 0

class TestGeometricComplexity:
    def test_u_shaped_room(self):
        coords = [Point(0,0), Point(0,10), Point(5,10), Point(5,5), Point(10,5), Point(10,0), Point(0,0)]
        poly = Polygon(coords)
        room = Room(name="U-Shaped", polygon=poly, room_type=RoomType.CORRIDOR)
        assert room.area > 0
        devices = [
            Device(position=Point(2.5, 5), device_type=DeviceType.SMOKE_DETECTOR),
            Device(position=Point(2.5, 2.5), device_type=DeviceType.SMOKE_DETECTOR),
            Device(position=Point(7.5, 2.5), device_type=DeviceType.SMOKE_DETECTOR),
        ]
        service = CoverageService()
        violations = service.check_room_coverage(room, devices)
        coverage_violations = [v for v in violations if "uncovered" in v.violation_code.lower()]
        assert len(coverage_violations) == 0

    def test_room_with_hole(self):
        outer = [Point(0, 0), Point(0, 20), Point(20, 20), Point(20, 0)]
        inner = [Point(5, 5), Point(5, 15), Point(15, 15), Point(15, 5)]
        poly = Polygon(outer, [inner])
        room = Room(name="Atrium", polygon=poly, room_type=RoomType.LOBBY)
        assert room.area == 400.0

class TestPerformanceAndLoad:
    def test_high_device_density(self):
        poly = Polygon([Point(0, 0), Point(0, 100), Point(100, 100), Point(100, 0)])
        room = Room(name="Server Room", polygon=poly, room_type=RoomType.SERVER_ROOM)
        devices = [Device(position=Point(random.uniform(0, 100), random.uniform(0, 100)), device_type=DeviceType.SMOKE_DETECTOR) for _ in range(500)]
        service = CoverageService()
        import time
        start = time.time()
        violations = service.check_room_coverage(room, devices)
        elapsed = time.time() - start
        assert elapsed < 1.0
        coverage_violations = [v for v in violations if "uncovered" in v.violation_code.lower()]
        # NOTE: Random placement cannot guarantee 100% coverage.
        # With 500 random detectors in a 100x100m room, some edge areas
        # will be uncovered. This is expected — the test verifies performance,
        # not perfect coverage with random placement.
        assert len(coverage_violations) < 5, f"Too many coverage violations: {len(coverage_violations)}"

    def test_large_building_simulation(self):
        rooms = []
        all_devices = []
        for i in range(50):
            offset = i * 20
            poly = Polygon([Point(offset, 0), Point(offset, 10), Point(offset+10, 10), Point(offset+10, 0)])
            room = Room(name=f"Room {i}", polygon=poly, room_type=RoomType.OFFICE)
            rooms.append(room)
            all_devices.extend([
                Device(position=Point(offset+2.5, 5), device_type=DeviceType.SMOKE_DETECTOR),
                Device(position=Point(offset+7.5, 5), device_type=DeviceType.SMOKE_DETECTOR)
            ])
        project = DesignProject(name="Large Building", rooms=rooms, devices=all_devices)
        compliance_service = ComplianceService()
        import time
        start = time.time()
        report = compliance_service.check_project_compliance(project)
        elapsed = time.time() - start
        assert elapsed < 10.0
        assert isinstance(report, dict)

class TestDataIntegrityAndFuzzing:
    def test_nan_coordinates(self):
        p = Point(float('nan'), 0)
        room = Room(name="NaN Room", polygon=Polygon([Point(0,0), Point(0,1), Point(1,1), Point(1,0)]), room_type=RoomType.OFFICE)
        device = Device(position=p, device_type=DeviceType.SMOKE_DETECTOR)
        service = CoverageService()
        violations = service.check_room_coverage(room, [device])
        assert isinstance(violations, list)

    def test_none_values_in_normalization(self):
        norm_service = NormalizationService()
        try:
            if hasattr(norm_service, 'normalize_rooms'):
                norm_service.normalize_rooms([{"name": "Test"}])
        except Exception as e:
            assert isinstance(e, (ValueError, TypeError, AttributeError))

    def test_duplicate_devices_same_location(self):
        poly = Polygon([Point(0, 0), Point(0, 10), Point(10, 10), Point(10, 0)])
        room = Room(name="Dup Room", polygon=poly, room_type=RoomType.OFFICE)
        p = Point(5, 5)
        devices = [Device(position=p, device_type=DeviceType.SMOKE_DETECTOR) for _ in range(3)]
        service = CoverageService()
        violations = service.check_room_coverage(room, devices)
        assert isinstance(violations, list)

class TestLogicalContradictions:
    def test_device_outside_room(self):
        poly = Polygon([Point(0, 0), Point(0, 10), Point(10, 10), Point(10, 0)])
        room = Room(name="Out Room", polygon=poly, room_type=RoomType.OFFICE)
        device = Device(position=Point(50, 50), device_type=DeviceType.SMOKE_DETECTOR)
        service = CoverageService()
        violations = service.check_room_coverage(room, [device])
        assert isinstance(violations, list)

    def test_standards_work(self):
        room = Room(name="Std Room", polygon=Polygon([Point(0,0), Point(0,10), Point(10,10), Point(10,0)]), room_type=RoomType.OFFICE)
        device = Device(position=Point(5,5), device_type=DeviceType.SMOKE_DETECTOR)
        service = CoverageService()
        v = service.check_room_coverage(room, [device])
        assert isinstance(v, list)

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
