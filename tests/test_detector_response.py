"""
tests/test_detector_response.py
================================
Comprehensive test suite for fireai/core/detector_response.py

SAFETY CRITICAL: Detector response time estimates are used in ASET/RSET
analysis. Overestimated response times make the design appear safer than it
is; underestimated times waste resources. These are ENGINEERING ESTIMATES
only — never the sole basis for life safety decisions.

NFPA 72 References:
  §17.7   — Detection Principles
  §17.7.3 — Heat Detectors
  §17.7.4 — Smoke Detectors
  Alpert's ceiling jet correlation
  RTI model (Heskestad)
"""

from __future__ import annotations

import math
import pytest

from fireai.core.detector_response import (
    calculate_heat_detector_response,
    calculate_smoke_detector_response,
    DetectorResponseResult,
    _RESPONSE_TIME_SAFETY_MARGIN,
    _RTI_SPOT_HEAT_LOW,
    _RTI_SPOT_HEAT_MED,
    _RTI_SPOT_HEAT_HIGH,
    _AMBIENT_TEMP_C,
    _G,
)


# ─────────────────────────────────────────────────────────────────────────────
# Heat Detector Response (Alpert + RTI Model)
# ─────────────────────────────────────────────────────────────────────────────


class TestCalculateHeatDetectorResponse:
    """
    NFPA 72 §17.7.3 — Heat detector activation using Alpert's ceiling jet
    model and the RTI (Response Time Index) model.
    """

    def test_basic_heat_detector(self):
        """Standard fire: 500kW, 3m ceiling, 2m from plume, RTI=50."""
        result = calculate_heat_detector_response(
            fire_hrr_kw=500.0,
            ceiling_height_m=3.0,
            distance_to_fire_m=2.0,
            rti=50.0,
            activation_temp_c=57.0,
            ambient_temp_c=30.0,
        )
        assert result.activation_time_s > 0
        assert result.safety_margin_s > 0
        assert result.total_with_margin > result.activation_time_s
        assert result.model_used == "Alpert_ceiling_jet_RTI"
        assert result.detector_type == "heat"
        assert result.nfpa_section == "NFPA 72 §17.7.3"

    def test_near_plume_model(self):
        """r/H ≤ 0.2 uses near-plume formula.
        r=0.5m, H=3m → r/H = 0.167 ≤ 0.2
        """
        result = calculate_heat_detector_response(
            fire_hrr_kw=500.0,
            ceiling_height_m=3.0,
            distance_to_fire_m=0.5,
        )
        assert result.activation_time_s > 0
        assert result.activation_possible is True

    def test_far_from_plume_model(self):
        """r/H > 0.2 uses far-from-plume formula.
        r=3m, H=3m → r/H = 1.0 > 0.2
        """
        result = calculate_heat_detector_response(
            fire_hrr_kw=500.0,
            ceiling_height_m=3.0,
            distance_to_fire_m=3.0,
        )
        assert result.activation_time_s > 0

    def test_larger_fire_activates_faster(self):
        """Higher HRR → higher ceiling jet temperature → faster activation."""
        r_low = calculate_heat_detector_response(
            fire_hrr_kw=200.0,
            ceiling_height_m=3.0,
            distance_to_fire_m=2.0,
        )
        r_high = calculate_heat_detector_response(
            fire_hrr_kw=2000.0,
            ceiling_height_m=3.0,
            distance_to_fire_m=2.0,
        )
        assert r_high.activation_time_s < r_low.activation_time_s

    def test_closer_detector_activates_faster(self):
        """Detector closer to fire activates sooner."""
        r_far = calculate_heat_detector_response(
            fire_hrr_kw=500.0,
            ceiling_height_m=3.0,
            distance_to_fire_m=5.0,
        )
        r_near = calculate_heat_detector_response(
            fire_hrr_kw=500.0,
            ceiling_height_m=3.0,
            distance_to_fire_m=1.0,
        )
        assert r_near.activation_time_s <= r_far.activation_time_s

    def test_lower_rti_faster_response(self):
        """Low RTI (fast detector) → shorter activation time."""
        r_high_rti = calculate_heat_detector_response(
            fire_hrr_kw=500.0,
            ceiling_height_m=3.0,
            distance_to_fire_m=2.0,
            rti=120.0,
        )
        r_low_rti = calculate_heat_detector_response(
            fire_hrr_kw=500.0,
            ceiling_height_m=3.0,
            distance_to_fire_m=2.0,
            rti=15.0,
        )
        assert r_low_rti.activation_time_s < r_high_rti.activation_time_s

    def test_higher_ceiling_slower_response(self):
        """Higher ceiling → cooler ceiling jet → slower activation."""
        r_low = calculate_heat_detector_response(
            fire_hrr_kw=500.0,
            ceiling_height_m=3.0,
            distance_to_fire_m=2.0,
        )
        r_high = calculate_heat_detector_response(
            fire_hrr_kw=500.0,
            ceiling_height_m=6.0,
            distance_to_fire_m=2.0,
        )
        assert r_high.activation_time_s >= r_low.activation_time_s

    def test_non_activating_detector(self):
        """V96 FIX: When gas temp never reaches activation temp.
        Very small fire, high ceiling → gas temperature < 57°C.
        """
        result = calculate_heat_detector_response(
            fire_hrr_kw=10.0,
            ceiling_height_m=10.0,
            distance_to_fire_m=8.0,
            activation_temp_c=57.0,
        )
        assert result.activation_possible is False
        assert result.activation_time_s == float("inf")
        assert result.safety_margin_s == float("inf")
        assert result.total_with_margin == float("inf")

    def test_safety_margin_25_percent(self):
        """Safety margin must be exactly 25% of activation time."""
        result = calculate_heat_detector_response(
            fire_hrr_kw=500.0,
            ceiling_height_m=3.0,
            distance_to_fire_m=2.0,
        )
        if result.activation_possible:
            expected_margin = result.activation_time_s * _RESPONSE_TIME_SAFETY_MARGIN
            assert result.safety_margin_s == pytest.approx(expected_margin, rel=1e-3)
            assert result.total_with_margin == pytest.approx(
                result.activation_time_s + result.safety_margin_s, rel=1e-3
            )

    def test_negative_hrr_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_heat_detector_response(fire_hrr_kw=-100.0, ceiling_height_m=3.0, distance_to_fire_m=2.0)

    def test_zero_hrr_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_heat_detector_response(fire_hrr_kw=0.0, ceiling_height_m=3.0, distance_to_fire_m=2.0)

    def test_nan_hrr_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_heat_detector_response(fire_hrr_kw=float("nan"), ceiling_height_m=3.0, distance_to_fire_m=2.0)

    def test_inf_hrr_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_heat_detector_response(fire_hrr_kw=float("inf"), ceiling_height_m=3.0, distance_to_fire_m=2.0)

    def test_negative_ceiling_height_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_heat_detector_response(fire_hrr_kw=500.0, ceiling_height_m=-3.0, distance_to_fire_m=2.0)

    def test_zero_ceiling_height_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_heat_detector_response(fire_hrr_kw=500.0, ceiling_height_m=0.0, distance_to_fire_m=2.0)

    def test_nan_ceiling_height_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_heat_detector_response(fire_hrr_kw=500.0, ceiling_height_m=float("nan"), distance_to_fire_m=2.0)

    def test_negative_distance_raises(self):
        with pytest.raises(ValueError, match="non-negative finite"):
            calculate_heat_detector_response(fire_hrr_kw=500.0, ceiling_height_m=3.0, distance_to_fire_m=-1.0)

    def test_nan_distance_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            calculate_heat_detector_response(fire_hrr_kw=500.0, ceiling_height_m=3.0, distance_to_fire_m=float("nan"))

    def test_zero_rti_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_heat_detector_response(fire_hrr_kw=500.0, ceiling_height_m=3.0, distance_to_fire_m=2.0, rti=0.0)

    def test_negative_rti_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_heat_detector_response(fire_hrr_kw=500.0, ceiling_height_m=3.0, distance_to_fire_m=2.0, rti=-10.0)

    def test_nan_activation_temp_raises(self):
        with pytest.raises(ValueError, match="finite"):
            calculate_heat_detector_response(
                fire_hrr_kw=500.0, ceiling_height_m=3.0, distance_to_fire_m=2.0,
                activation_temp_c=float("nan"),
            )

    def test_nan_ambient_temp_raises(self):
        with pytest.raises(ValueError, match="finite"):
            calculate_heat_detector_response(
                fire_hrr_kw=500.0, ceiling_height_m=3.0, distance_to_fire_m=2.0,
                ambient_temp_c=float("nan"),
            )

    def test_zero_distance_plume_center(self):
        """Detector directly above fire plume axis."""
        result = calculate_heat_detector_response(
            fire_hrr_kw=500.0,
            ceiling_height_m=3.0,
            distance_to_fire_m=0.0,
        )
        assert result.activation_possible is True
        assert result.activation_time_s > 0

    def test_result_fields_populated(self):
        result = calculate_heat_detector_response(500.0, 3.0, 2.0)
        assert result.fire_hrr_kw == 500.0
        assert result.distance_to_fire_m == 2.0
        assert result.ceiling_height_m == 3.0


# ─────────────────────────────────────────────────────────────────────────────
# Smoke Detector Response (Zukoski Plume + Alpert Ceiling Jet)
# ─────────────────────────────────────────────────────────────────────────────


class TestCalculateSmokeDetectorResponse:
    """
    NFPA 72 §17.7.4 — Smoke detector activation using plume transport model.
    """

    def test_basic_smoke_detector(self):
        result = calculate_smoke_detector_response(
            fire_hrr_kw=500.0,
            ceiling_height_m=3.0,
            distance_to_fire_m=5.0,
        )
        assert result.activation_time_s > 0
        assert result.safety_margin_s > 0
        assert result.total_with_margin > result.activation_time_s
        assert result.model_used == "Zukoski_plume_Alpert_ceiling_jet"
        assert result.detector_type == "smoke"
        assert result.nfpa_section == "NFPA 72 §17.7.4"

    def test_smoke_faster_than_heat(self):
        """Smoke detectors generally respond faster than heat detectors."""
        smoke = calculate_smoke_detector_response(500.0, 3.0, 2.0)
        heat = calculate_heat_detector_response(500.0, 3.0, 2.0)
        # Smoke detectors should activate faster (shorter time)
        if heat.activation_possible and smoke.activation_possible:
            assert smoke.activation_time_s < heat.activation_time_s

    def test_larger_fire_faster_smoke_transport(self):
        """Higher HRR → faster plume velocity → faster smoke arrival."""
        r_low = calculate_smoke_detector_response(200.0, 3.0, 2.0)
        r_high = calculate_smoke_detector_response(2000.0, 3.0, 2.0)
        assert r_high.activation_time_s < r_low.activation_time_s

    def test_higher_ceiling_slower_smoke_arrival(self):
        """Higher ceiling → longer plume rise time."""
        r_low = calculate_smoke_detector_response(500.0, 3.0, 2.0)
        r_high = calculate_smoke_detector_response(500.0, 6.0, 2.0)
        assert r_high.activation_time_s > r_low.activation_time_s

    def test_farther_detector_slower_transport(self):
        """Detector farther from fire → longer ceiling jet transport."""
        r_near = calculate_smoke_detector_response(500.0, 3.0, 1.0)
        r_far = calculate_smoke_detector_response(500.0, 3.0, 10.0)
        assert r_far.activation_time_s > r_near.activation_time_s

    def test_safety_margin_applied(self):
        result = calculate_smoke_detector_response(500.0, 3.0, 2.0)
        expected_margin = result.activation_time_s * _RESPONSE_TIME_SAFETY_MARGIN
        assert result.safety_margin_s == pytest.approx(expected_margin, rel=1e-3)

    def test_negative_hrr_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_smoke_detector_response(-100.0, 3.0, 2.0)

    def test_zero_hrr_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_smoke_detector_response(0.0, 3.0, 2.0)

    def test_nan_hrr_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_smoke_detector_response(float("nan"), 3.0, 2.0)

    def test_inf_hrr_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_smoke_detector_response(float("inf"), 3.0, 2.0)

    def test_negative_ceiling_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_smoke_detector_response(500.0, -3.0, 2.0)

    def test_zero_ceiling_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_smoke_detector_response(500.0, 0.0, 2.0)

    def test_nan_ceiling_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_smoke_detector_response(500.0, float("nan"), 2.0)

    def test_negative_distance_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            calculate_smoke_detector_response(500.0, 3.0, -1.0)

    def test_nan_distance_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            calculate_smoke_detector_response(500.0, 3.0, float("nan"))

    def test_inf_distance_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            calculate_smoke_detector_response(500.0, 3.0, float("inf"))

    def test_zero_distance_directly_above_fire(self):
        """Detector directly above fire → only plume rise time."""
        result = calculate_smoke_detector_response(500.0, 3.0, 0.0)
        assert result.activation_time_s > 0

    def test_near_plume_smoke(self):
        """r/H ≤ 0.2 → near plume ceiling jet velocity."""
        result = calculate_smoke_detector_response(500.0, 3.0, 0.5)
        assert result.activation_time_s > 0

    def test_result_fields_populated(self):
        result = calculate_smoke_detector_response(500.0, 3.0, 2.0)
        assert result.fire_hrr_kw == 500.0
        assert result.distance_to_fire_m == 2.0
        assert result.ceiling_height_m == 3.0
        assert result.activation_possible is True


# ─────────────────────────────────────────────────────────────────────────────
# DetectorResponseResult (frozen dataclass)
# ─────────────────────────────────────────────────────────────────────────────


class TestDetectorResponseResultFrozen:
    def test_immutable(self):
        result = calculate_heat_detector_response(500.0, 3.0, 2.0)
        with pytest.raises(AttributeError):
            result.activation_time_s = 999.0

    def test_has_all_fields(self):
        result = calculate_heat_detector_response(500.0, 3.0, 2.0)
        assert hasattr(result, "activation_time_s")
        assert hasattr(result, "safety_margin_s")
        assert hasattr(result, "total_with_margin")
        assert hasattr(result, "activation_possible")
        assert hasattr(result, "model_used")
        assert hasattr(result, "detector_type")
        assert hasattr(result, "fire_hrr_kw")
        assert hasattr(result, "distance_to_fire_m")
        assert hasattr(result, "ceiling_height_m")
        assert hasattr(result, "nfpa_section")


# ─────────────────────────────────────────────────────────────────────────────
# Constants Verification
# ─────────────────────────────────────────────────────────────────────────────


class TestConstants:
    def test_safety_margin(self):
        assert _RESPONSE_TIME_SAFETY_MARGIN == 0.25

    def test_rti_values_ordering(self):
        """RTI values should be ordered: LOW < MED < HIGH."""
        assert _RTI_SPOT_HEAT_LOW < _RTI_SPOT_HEAT_MED < _RTI_SPOT_HEAT_HIGH

    def test_ambient_temp_realistic(self):
        """V96 FIX: Default ambient should be realistic (30°C, not 20°C)."""
        assert _AMBIENT_TEMP_C == 30.0

    def test_gravity_constant(self):
        assert _G == pytest.approx(9.81)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
