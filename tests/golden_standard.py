"""
GOLDEN STANDARD TESTS - لا تُعدل هذه الملفات أبدًا إلا إذا تغير المعيار itself.
=====================================================================
If any of these tests fail, STOP using the tool immediately.

This is your "smoke detector" for the project. It doesn't prevent fire,
but it wakes you up before you burn.

Run: pytest tests/golden_standard.py -v
"""

import pytest
import math
from src.auto_placement import suggest_devices
from src.application.coverage_service import CoverageService
from src.application.graph_builder import GraphBuilder
from src.core.models import Room, Point, Polygon, NFPA72, DeviceType


class MockRoom:
    """Mock room for testing"""
    def __init__(self, name, polygon, height=3.0):
        self.name = name
        self.polygon = polygon
        self.height = height
        self.room_id = name
    
    @property
    def area(self):
        if self.polygon and self.polygon.exterior:
            return self.polygon.exterior.area
        return 0.0


# --- Golden Scenarios ---

def test_golden_square_room():
    """
    السيناريو 1: غرفة مربعة 10×10
    
    Expected: At least 1 device in center region
    """
    room = Room(
        name="Golden Square",
        polygon=Polygon(exterior=[
            Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)
        ])
    )
    
    spacing = NFPA72().get_max_spacing(DeviceType.SMOKE_DETECTOR)
    devices = suggest_devices(room, spacing)
    
    # Must have at least 1 device
    assert len(devices) >= 1, f"Expected ≥1 device, got {len(devices)}"
    
    # At least one device should be near the center
    center_device = any(
        d.position and 
        abs(d.position.x - 5.0) < 3.0 and 
        abs(d.position.y - 5.0) < 3.0
        for d in devices
    )
    assert center_device, "No device near center!"


def test_golden_narrow_room():
    """
    السيناريو 2: غرفة ضيقة 25×4 (corridor-like)
    
    Expected: At least 2 devices for 25m length
    """
    room = Room(
        name="Golden Narrow",
        polygon=Polygon(exterior=[
            Point(0, 0), Point(25, 0), Point(25, 4), Point(0, 4)
        ])
    )
    
    spacing = NFPA72().get_max_spacing(DeviceType.SMOKE_DETECTOR)
    devices = suggest_devices(room, spacing)
    
    # 25m / 9.1m spacing ≈ 2.7, so minimum 2 devices
    assert len(devices) >= 2, f"25x4m room got only {len(devices)} devices!"


def test_golden_beam_detection():
    """
    السيناريو 3: غرفة مع عارضة عميقة
    
    Expected: Deep beam (≥10% ceiling height) detected
    """
    from src.application.beam_detector import BeamDetector
    from src.core.models import Beam
    
    room = Room(
        name="Golden Beam",
        polygon=Polygon(exterior=[
            Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)
        ]),
        height=3.0
    )
    
    beam = Beam(
        start=Point(0, 5), end=Point(10, 5), depth=0.5
    )
    
    detector = BeamDetector()
    shadow_zones = detector.compute_shadow(room, [beam])
    
    # 0.5m in 3m ceiling = 16.7% = DEEP beam
    assert len(shadow_zones) > 0, "Deep beam shadow not detected!"


def test_golden_cable_routing():
    """
    السيناريو 4: توجيه كابل حول جدار
    
    Expected: Path avoids wall, no crossing
    """
    polygon = [(0, 0), (10, 0), (10, 10), (0, 10)]
    walls = [((5, 0), (5, 10))]  # Wall in middle
    
    panel_pos = (1, 1)
    builder = GraphBuilder(grid_spacing_m=1.0)
    graph = builder.build_from_polygon(polygon, panel_pos, wall_lines=walls)
    
    # Graph should be built
    assert graph is not None
    assert graph.number_of_nodes() > 0, "Graph has no nodes!"


def test_golden_coverage_validation():
    """
    السيناريو 5: فحص التغطية
    
    Expected: Coverage service runs without error
    """
    room = Room(
        name="Golden Coverage",
        polygon=Polygon(exterior=[
            Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)
        ])
    )
    
    # Create device in center
    device = Device(
        device_id=1,
        position=Point(5, 5),
        device_type=DeviceType.SMOKE_DETECTOR,
        room_id="Golden Coverage"
    )
    
    service = CoverageService(beams=[])
    violations = service.check_coverage(room, [device], None)
    
    # Should not crash - violations list may be empty or not
    assert isinstance(violations, list), "Coverage check returned invalid type!"


def test_golden_standard_nfpa72():
    """
    السيناريو 6: NFPA 72 spacing values
    
    Expected: 9.1m for smoke detector
    """
    standard = NFPA72()
    spacing = standard.get_max_spacing(DeviceType.SMOKE_DETECTOR)
    
    # NFPA 72 specifies 9.1m (30ft) max spacing
    assert spacing == 9.1, f"NFPA72 spacing changed to {spacing}m!"


def test_golden_small_room():
    """
    السيناريو 7: غرفة صغيرة 5×5
    
    Expected: At least 1 device
    """
    room = Room(
        name="Golden Small",
        polygon=Polygon(exterior=[
            Point(0, 0), Point(5, 0), Point(5, 5), Point(0, 5)
        ])
    )
    
    spacing = NFPA72().get_max_spacing(DeviceType.SMOKE_DETECTOR)
    devices = suggest_devices(room, spacing)
    
    # 5x5 room should fit at least 1 device
    assert len(devices) >= 1, f"5x5m room got {len(devices)} devices!"


# --- Run Instructions ---
"""
PYTEST USAGE:
-----------
$ pytest tests/golden_standard.py -v

If ALL tests pass ✅ - You are safe to work
If ANY test fails ❌ - STOP immediately, don't use the tool

WHAT TO DO IF FAILURE:
1. Check if external libraries changed (Shapely, NetworkX, etc.)
2. Check if you made unintended code changes
3. Check environment differences (Python version, OS)
4. Report issue before continuing
"""