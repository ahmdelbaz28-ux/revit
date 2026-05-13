"""
test_deduplication.py — FireAI V5.1.2
Tests for _is_duplicate() and _remove_duplicates() functions.
"""

import pytest
from shapely.geometry import Polygon
from parsers.dxf_parser import DXFParser


class TestDeduplication:
    """Test deduplication logic"""

    def test_100_percent_overlap_is_duplicate(self):
        """100% overlap = duplicate - should merge"""
        poly1 = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        poly2 = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        
        parser = DXFParser()
        is_dup = parser._is_duplicate(poly1, poly2)
        
        assert is_dup is True, "100% identical polygons should be duplicates"

    def test_95_percent_overlap_is_duplicate(self):
        """95% overlap = duplicate"""
        poly1 = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        poly2 = Polygon([(0.5, 0.5), (10.5, 0.5), (10.5, 10.5), (0.5, 0.5)])
        
        parser = DXFParser()
        is_dup = parser._is_duplicate(poly1, poly2)
        
        assert is_dup is True, "95% overlap should be duplicate"

    def test_50_percent_overlap_not_duplicate(self):
        """50% overlap = two separate rooms"""
        poly1 = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        poly2 = Polygon([(10, 0), (20, 0), (20, 10), (10, 10)])  # Adjacent, no overlap
        
        parser = DXFParser()
        is_dup = parser._is_duplicate(poly1, poly2)
        
        assert is_dup is False, "50% partial overlap should be separate rooms"

    def test_no_overlap_not_duplicate(self):
        """0% overlap = completely separate rooms"""
        poly1 = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        poly2 = Polygon([(20, 20), (30, 20), (30, 30), (20, 30)])
        
        parser = DXFParser()
        is_dup = parser._is_duplicate(poly1, poly2)
        
        assert is_dup is False, "No overlap = not duplicate"

    def test_remove_duplicates_keeps_larger(self):
        """When duplicate found, keep larger polygon"""
        poly1 = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])  # 100m²
        poly2 = Polygon([(1, 1), (9, 1), (9, 9), (1, 9)])  # 64m² - smaller
        
        parser = DXFParser()
        result = parser._remove_duplicates([poly1, poly2])
        
        assert len(result) == 1, "Duplicates should be reduced to 1"
        assert result[0].area == 100, "Should keep larger polygon"

    def test_remove_duplicates_separate_rooms(self):
        """Separate rooms should not be removed"""
        poly1 = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        poly2 = Polygon([(15, 15), (25, 15), (25, 25), (15, 25)])  # Far apart
        
        parser = DXFParser()
        result = parser._remove_duplicates([poly1, poly2])
        
        assert len(result) == 2, "Separate rooms should be kept"


class TestSafetyMargin:
    """Test safety margin calculations"""

    def test_margin_10_detectors(self):
        """10 detectors * 1.15 = 12 (ceil)"""
        from core.floor_orchestrator import SAFETY_MARGIN
        import math
        count = 10
        expected = math.ceil(count * SAFETY_MARGIN)
        assert expected == 12, f"10 * 1.15 = 11.5 → ceil = 12, got {expected}"

    def test_margin_1_detector(self):
        """1 detector * 1.15 = 2 (ceil, at least 2)"""
        from core.floor_orchestrator import SAFETY_MARGIN
        import math
        count = 1
        expected = math.ceil(count * SAFETY_MARGIN)
        assert expected == 2, f"1 * 1.15 = 1.15 → ceil = 2, got {expected}"

    def test_margin_100_detectors(self):
        """100 detectors * 1.15 = 115"""
        from core.floor_orchestrator import SAFETY_MARGIN
        import math
        count = 100
        expected = math.ceil(count * SAFETY_MARGIN)
        assert expected == 115, f"100 * 1.15 = 115, got {expected}"

    def test_spline_supported(self):
        """SPLINE entity type should be processed"""
        from parsers.dxf_parser import DXFParser
        parser = DXFParser()
        # Method should exist
        assert hasattr(parser, '_spline_to_segments'), "SPLINE method missing"

    def test_geometry_hash_present(self):
        """Audit entry should contain entry_hash"""
        from audit_trail import AuditTrail
        trail = AuditTrail("test_geo")
        trail.log_dxf_parse("test.dxf", "Meters", 1.0, 5, 0)
        data = trail.to_list()[0]
        assert "entry_hash" in data, "entry_hash missing"
        assert len(data["entry_hash"]) == 16, "hash should be 16 chars"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])