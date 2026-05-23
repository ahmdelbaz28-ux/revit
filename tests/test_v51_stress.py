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
    """Ceiling height tests aligned with V20.2 corrected RADIUS_MAP.

    V20.2 FIX: R = 0.7 × adjusted_spacing per NFPA 72 Table 17.6.3.1.1.
    Height 15.0m falls in bracket (12.2, 15.24) → R = 0.7 × 5.20 = 3.64.
    Heights below 3.0m are handled safely by get_smoke_detector_radius()
    which returns the conservative 3.0m-bracket value (6.37m) rather than
    raising an exception — this is the correct V20.2 behaviour.
    """

    def test_15m_returns_correct_v20_2_radius(self):
        """15.0m is in (12.2, 15.24) bracket → R = 0.7 × 5.20 = 3.64."""
        r = get_smoke_detector_radius(15.0)
        assert r == 3.64, f"Expected 3.64 per V20.2 fix, got {r}"

    def test_above_15_24m_raises(self):
        """Heights above NFPA 72 max (15.24m) must raise CeilingHeightError."""
        from fireai.core.nfpa72_models import CeilingHeightError
        with pytest.raises(CeilingHeightError):
            get_smoke_detector_radius(50.0)

    def test_below_3m_returns_conservative_radius(self):
        """Heights below 3.0m get safe conservative radius via V20.2 fix.

        get_smoke_detector_radius() returns R for the ≤3.0m bracket (6.37m).
        Use get_smoke_detector_radius_safe() for flag/review detection.
        """
        from fireai.core.nfpa72_models import get_smoke_detector_radius_safe
        r, details = get_smoke_detector_radius_safe(2.5, _return_details=True)
        assert r == 6.37, f"Conservative radius for 2.5m should be 6.37, got {r}"
        assert details.get("flag") is not None, "Below 3m should produce a PE review flag"
        assert details.get("conservative") is True, "Below 3m should be marked conservative"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])