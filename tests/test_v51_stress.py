"""
tests/test_v51_stress.py — FireAI V5.1.2 Stress Tests
Critical safety checks only. NO safety margin - NFPA compliance via verify_full_coverage().

V24 UPDATE: Tests now validate the CORRECT strict/safe API separation:
  - get_smoke_detector_radius() is STRICT: raises CeilingHeightError for h < 3.0m
  - get_smoke_detector_radius_safe() is GRACEFUL: returns conservative value + PE flag
  - RADIUS_MAP brackets corrected to start at 3.0m (not 0.0m)
  - (12.2, 15.24] bracket uses R = 0.7 × 5.20 = 3.64 (CONSERVATIVE EXTRAPOLATION)
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
    """Ceiling height tests aligned with V24 corrected RADIUS_MAP.

    V24 SAFETY FIX: get_smoke_detector_radius() is STRICT per NFPA 72.
    Heights below 3.0m are OUTSIDE the standard's scope and MUST raise
    CeilingHeightError — NOT silently return a value. The old (0.0, 3.0)
    bracket was a LIFE-SAFETY GAP that accepted h=0.1m without warning.
    Use get_smoke_detector_radius_safe() for graceful handling.
    """

    def test_15m_returns_correct_v24_radius(self):
        """15.0m is in (12.2, 15.24] bracket → R = 0.7 × 5.20 = 3.64.
        CONSERVATIVE EXTRAPOLATION: heights >12.2m require safer (smaller) spacing
        per NFPA 72 extrapolation rules. More detectors = safer."""
        r = get_smoke_detector_radius(15.0)
        assert r == 3.64, f"Expected 3.64 (conservative), got {r}"

    def test_above_15_24m_raises(self):
        """Heights above NFPA 72 max (15.24m) must raise CeilingHeightError."""
        from fireai.core.nfpa72_models import CeilingHeightError
        with pytest.raises(CeilingHeightError):
            get_smoke_detector_radius(50.0)

    def test_below_3m_raises(self):
        """Heights below 3.0m MUST raise CeilingHeightError in strict function.

        NFPA 72 Table 17.6.3.1.1 starts at h=3.0m. Any height below this
        is outside the standard's scope and must NOT silently return a value.
        Use get_smoke_detector_radius_safe() for graceful handling.
        """
        from fireai.core.nfpa72_models import CeilingHeightError
        with pytest.raises(CeilingHeightError):
            get_smoke_detector_radius(2.5)

    def test_safe_function_handles_below_3m_gracefully(self):
        """get_smoke_detector_radius_safe() returns conservative value + PE flag."""
        from fireai.core.nfpa72_models import get_smoke_detector_radius_safe
        r, details = get_smoke_detector_radius_safe(2.5, _return_details=True)
        assert r == 6.37, f"Conservative radius for 2.5m should be 6.37, got {r}"
        assert details.get("flag") is not None, "Below 3m should produce a PE review flag"
        assert details.get("conservative") is True, "Below 3m should be marked conservative"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
