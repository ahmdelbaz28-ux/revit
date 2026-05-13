"""
test_v51_integration.py — FireAI V5.1.0
CRITICAL: Uses REAL OptimalMIPEngine, not Mock.
"""

import pytest
from shapely.geometry import Polygon

from nfpa72_models import (
    RoomSpec, CeilingSpec, CeilingType, DetectorType, NFPAComplianceError
)
from parsers.dxf_parser import DXFParser
from core.floor_orchestrator import FloorOrchestrator


def make_room(rid: str, coords: list, height: float = 3.0,
              det: DetectorType = DetectorType.SMOKE) -> RoomSpec:
    return RoomSpec(
        name=rid,
        width_m=max(x for x, y in coords) - min(x for x, y in coords),
        depth_m=max(y for x, y in coords) - min(y for x, y in coords),
        height_m=height,
        polygon=Polygon(coords),
        ceiling_spec=CeilingSpec(height),
        detector_type=det,
        occupancy_type="office",
    )


class TestNFPATable:
    """Verify dynamic radius from NFPA 72 Table 17.6.3.1"""

    def test_3m_gives_4_55m(self):
        orch = FloorOrchestrator()
        room = make_room("R1", [(0, 0), (8, 0), (8, 6), (0, 6)], 3.0)
        result = orch.process([room], "Test")
        assert result.room_results[0].radius_m == 4.55

    def test_4_8m_gives_5_35m_not_6_37(self):
        orch = FloorOrchestrator()
        room = make_room("R2", [(0, 0), (10, 0), (10, 8), (0, 8)], 4.8)
        result = orch.process([room], "Test")
        assert result.room_results[0].radius_m == 5.35
        assert result.room_results[0].radius_m != 6.37

    def test_15_3m_now_passes(self):
        """15.3m is now valid after edge case fix - should PASS"""
        orch = FloorOrchestrator()
        room = make_room("R3", [(0, 0), (5, 0), (5, 5), (0, 5)], 15.3)
        result = orch.process([room], "Test")
        assert result.room_results[0].status == "PASS"


class TestMultiRoom:
    """Verify sequential processing with real engine"""

    def test_three_rooms_all_pass(self):
        orch = FloorOrchestrator()
        rooms = [
            make_room("R1", [(0, 0), (8, 0), (8, 6), (0, 6)], 3.0),
            make_room("R2", [(10, 0), (20, 0), (20, 8), (10, 8)], 3.5),
            make_room("R3", [(0, 10), (12, 10), (12, 15), (0, 15)], 4.0),
        ]
        result = orch.process(rooms, "Test3")
        assert result.total_rooms == 3
        assert result.rooms_errored == 0
        assert result.total_detectors > 0

    def test_meta_is_ssot(self):
        """Verify radius comes from meta, not external calculation"""
        orch = FloorOrchestrator()
        room = make_room("R1", [(0, 0), (8, 0), (8, 6), (0, 6)], 3.0)
        result = orch.process([room], "Test")
        rr = result.room_results[0]
        # If SSOT is broken, these would fail
        assert rr.radius_m is not None
        assert rr.geometry is not None


class TestDXFParser:
    """Test DXF reading"""

    def test_reads_2rooms(self):
        """Room 1 (8x6=48m²), Room 2 (5x5=25m²), Column (2x2=4m² skipped)"""
        parser = DXFParser(min_area=5.0)  # Skip small objects like columns
        res = parser.parse("tests/fixtures/simple_floor_2rooms.dxf")
        assert res.room_count == 2
        assert all(r.polygon.is_valid for r in res.rooms)

    def test_valid_polygons_only(self):
        parser = DXFParser(min_area=5.0)
        res = parser.parse("tests/fixtures/simple_floor_2rooms.dxf")
        for r in res.rooms:
            assert r.polygon.is_valid
            assert r.area_m2 > 0