# FireAI V8 Tests - Simple

import pytest
from nfpa72_coverage import adjust_coverage_for_beams
from nfpa72_models import (
    get_smoke_detector_radius_safe,
)
from src.auto_placement import suggest_duct_detectors, HVACDuct, HVACDuctType


class TestExtremeHeights:
    def test_height_24m(self):
        assert get_smoke_detector_radius_safe(24.0) == 6.4
    def test_negative(self):
        assert get_smoke_detector_radius_safe(-1.0) == 4.55
    def test_height_20m(self):
        assert get_smoke_detector_radius_safe(20.0) == 6.4
    def test_height_15_3m(self):
        assert get_smoke_detector_radius_safe(15.3) == 6.4
    def test_height_3m(self):
        assert get_smoke_detector_radius_safe(3.0) == 4.55
    def test_height_12m(self):
        assert get_smoke_detector_radius_safe(12.0) == 6.4


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
