# FireAI V8 Tests - Simple

import pytest
from nfpa72_coverage import adjust_coverage_for_beams
from nfpa72_models import (
    get_smoke_detector_radius_safe,
)
from src.auto_placement import suggest_duct_detectors, HVACDuct, HVACDuctType


class TestExtremeHeights:
    # FIX: Updated values after R = 0.7×S correction (was S/2 = 4.55m, now R = 6.37m at h=3.0m)
    # Per NFPA 72-2022 §17.7.4.2.3.1: R = 0.7 × listed_spacing
    def test_height_24m(self):
        # Above 15.24m: capped at 15.24m → R = 0.7 × 5.60 = 3.92m
        assert get_smoke_detector_radius_safe(24.0) == 3.92
    def test_negative(self):
        """Negative height → REJECT with ValueError."""
        with pytest.raises(ValueError, match="CEILING_HEIGHT_MUST_BE_POSITIVE"):
            get_smoke_detector_radius_safe(-1.0)
    def test_height_20m(self):
        # Above 15.24m: capped at 15.24m → R = 0.7 × 5.60 = 3.92m
        assert get_smoke_detector_radius_safe(20.0) == 3.92
    def test_height_15_3m(self):
        # h=15.3m in (12.2, 15.24) bracket → R = 0.7 × 5.60 = 3.92m
        assert get_smoke_detector_radius_safe(15.3) == 3.92
    def test_height_3m(self):
        # h=3.0m: R = 0.7 × 9.10 = 6.37m (was incorrectly 4.55m using S/2)
        assert get_smoke_detector_radius_safe(3.0) == 6.37
    def test_height_12m(self):
        # h=12.0m in (10.7, 12.2) bracket → R = 0.7 × 6.00 = 4.20m
        assert get_smoke_detector_radius_safe(12.0) == 4.20


class TestBeam:
    def test_shallow(self):
        assert adjust_coverage_for_beams(4.55, 0.1, 3.0) == 4.55
    def test_moderate(self):
        r = adjust_coverage_for_beams(4.55, 0.2, 3.0)
        assert abs(r - 4.55*0.85) < 0.01
    def test_no_change(self):
        result = adjust_coverage_for_beams(4.55, 0.4, 3.0)
        assert result == 4.55


class TestDuct:
    def test_short_duct(self):
        duct = HVACDuct(duct_id='D1', duct_type=HVACDuctType.SUPPLY,
                       start_x=0, start_y=0, start_z=3, end_x=10, end_y=0, end_z=3)
        devs = suggest_duct_detectors([duct])
        assert len(devs) >= 2
    def test_long_duct(self):
        duct = HVACDuct(duct_id='D2', duct_type=HVACDuctType.SUPPLY,
                       start_x=0, start_y=0, start_z=3, end_x=42, end_y=0, end_z=3)
        devs = suggest_duct_detectors([duct])
        assert len(devs) >= 3
    def test_none_raises(self):
        with pytest.raises(TypeError):
            suggest_duct_detectors(None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
