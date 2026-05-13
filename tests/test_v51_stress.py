"""
tests/test_v51_stress.py — FireAI V5.1.2 Stress Tests
Critical safety checks only.
"""

import pytest
import math
from pathlib import Path
from shapely.geometry import Polygon

from parsers.dxf_parser import DXFParser
from nfpa72_calculations import get_smoke_detector_radius
from core.floor_orchestrator import SAFETY_MARGIN
from audit_trail import AuditTrail

FIXTURES = Path("tests/fixtures")


class TestSafetyMarginEnforcement:
    """The +15% margin must be applied."""

    def test_margin_1_to_2(self):
        assert math.ceil(1 * SAFETY_MARGIN) == 2

    def test_margin_10_to_12(self):
        assert math.ceil(10 * SAFETY_MARGIN) == 12

    def test_margin_100_to_115(self):
        assert math.ceil(100 * SAFETY_MARGIN) == 115


class TestDeduplication:
    """Deduplication must work correctly."""

    def test_90_overlap_removed(self):
        parser = DXFParser()
        poly1 = Polygon([(0,0),(10,0),(10,10),(0,10)])
        poly2 = Polygon([(0,0),(9.9,0),(9.9,9.9),(0,9.9)])
        unique = parser._remove_duplicates([poly1, poly2])
        assert len(unique) == 1

    def test_separate_rooms_kept(self):
        parser = DXFParser()
        poly1 = Polygon([(0,0),(10,0),(10,10),(0,10)])
        poly2 = Polygon([(20,20),(30,20),(30,30),(20,30)])
        unique = parser._remove_duplicates([poly1, poly2])
        assert len(unique) == 2


class TestAuditTrailIntegrity:
    """Audit trail must be immutable."""

    def test_entry_hash_present(self):
        trail = AuditTrail("test")
        trail.log_dxf_parse("x.dxf", "m", 1.0, 1, 0)
        entry = trail.to_list()[0]
        assert "entry_hash" in entry

    def test_hash_changes_on_tamper(self):
        trail = AuditTrail("test")
        trail.log_radius_lookup("R1", 3.0, 4.55, "row1")
        entry = trail._entries[0]
        orig = entry.entry_hash
        entry.outputs["radius_m"] = 9.99
        assert entry._compute_hash() != orig


class TestCeilingHeight:
    def test_15m_returns_6_4(self):
        r = get_smoke_detector_radius(15.0)
        assert r == 6.4

    def test_above_15m_raises(self):
        from nfpa72_models import CeilingHeightError
        with pytest.raises(CeilingHeightError):
            get_smoke_detector_radius(50.0)

    def test_below_3m_raises(self):
        from nfpa72_models import CeilingHeightError
        with pytest.raises(CeilingHeightError):
            get_smoke_detector_radius(2.5)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])