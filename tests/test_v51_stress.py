"""
tests/test_v51_stress.py — FireAI V5.1.2 Stress Tests
Critical safety checks only. NO safety margin - NFPA compliance via verify_full_coverage().
"""

import pytest
import math
from pathlib import Path
from shapely.geometry import Polygon

from parsers.dxf_parser import DXFParser
from nfpa72_calculations import get_smoke_detector_radius
from fireai.core.audit_trail import AuditTrail

FIXTURES = Path("tests/fixtures")


class TestCoreFeatures:
    """Test core V5.1.2 features"""

    def test_deduplication_works(self):
        parser = DXFParser()
        poly1 = Polygon([(0,0),(10,0),(10,10),(0,10)])
        poly2 = Polygon([(0,0),(9.9,0),(9.9,9.9),(0,9.9)])
        unique = parser._remove_duplicates([poly1, poly2])
        assert len(unique) == 1, "90%+ overlap should merge"

    def test_separate_rooms_kept(self):
        parser = DXFParser()
        poly1 = Polygon([(0,0),(10,0),(10,10),(0,10)])
        poly2 = Polygon([(20,20),(30,20),(30,30),(20,30)])
        unique = parser._remove_duplicates([poly1, poly2])
        assert len(unique) == 2, "Separate rooms must be kept"

    def test_audit_hash_present(self):
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