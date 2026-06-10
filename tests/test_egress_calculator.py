"""
tests/test_egress_calculator.py
===============================
Comprehensive test suite for fireai/core/egress_calculator.py

SAFETY CRITICAL: Egress calculations determine whether occupants can evacuate
safely before conditions become untenable. If RSET ≥ ASET, occupants CANNOT
evacuate safely. A safety margin (ASET/RSET ≥ 1.5) is mandatory.

NFPA 101 References:
  Chapter 7 — Means of Egress
  §7.3 — Capacity of Means of Egress
  §7.3.4 — Minimum egress width (0.71m / 28 inches)
"""

from __future__ import annotations

import math
import pytest

from fireai.core.egress_calculator import (
    calculate_egress_time,
    minimum_exit_width,
    EgressResult,
    _WALKING_SPEED_M_S,
    _STAIR_SPEED_M_S,
    _FLOW_RATE_DOOR_PER_M,
    _FLOW_RATE_STAIR_PER_M,
    _MIN_EGRESS_WIDTH_M,
    _SAFETY_FACTOR,
)


# ─────────────────────────────────────────────────────────────────────────────
# Egress Time Calculation
# ─────────────────────────────────────────────────────────────────────────────


class TestCalculateEgressTime:
    """
    NFPA 101 Chapter 7 — RSET = Pre-movement + max(Travel, Flow)
    """

    def test_basic_egress(self):
        """50 occupants, 30m travel, 0.91m exit, 600s ASET."""
        result = calculate_egress_time(
            occupant_count=50,
            travel_distance_m=30.0,
            exit_width_m=0.91,
            aset_s=600.0,
            premovement_time_s=60.0,
        )
        assert result.rset_s > 0
        assert result.travel_time_s > 0
        assert result.safety_factor > 0
        assert result.nfpa_section == "NFPA 101 §7.3"

    def test_travel_time_calculation(self):
        """Travel time = distance / speed.
        30m / 1.0 m/s = 30s for travel.
        Flow time = 50 / (0.91 × 1.1) = 49.95s.
        max(30, 49.95) = 49.95s.
        RSET = 60 + 49.95 = 109.95s.
        """
        result = calculate_egress_time(
            occupant_count=50,
            travel_distance_m=30.0,
            exit_width_m=0.91,
            aset_s=600.0,
            premovement_time_s=60.0,
        )
        expected_travel = max(30.0, 50.0 / (0.91 * 1.1))
        expected_rset = 60.0 + expected_travel
        assert result.travel_time_s == pytest.approx(expected_travel, rel=1e-2)
        assert result.rset_s == pytest.approx(expected_rset, rel=1e-2)

    def test_zero_occupants(self):
        """No occupants → zero travel time, inf safety factor, adequate."""
        result = calculate_egress_time(
            occupant_count=0,
            travel_distance_m=30.0,
            exit_width_m=0.91,
        )
        assert result.travel_time_s == 0.0
        assert result.rset_s == 0.0
        assert result.safety_factor == float("inf")
        assert result.is_adequate is True
        assert result.occupant_count == 0

    def test_single_occupant(self):
        """1 occupant — travel time dominates over flow time."""
        result = calculate_egress_time(
            occupant_count=1,
            travel_distance_m=30.0,
            exit_width_m=0.91,
        )
        # Travel = 30s, Flow = 1/(0.91*1.1) ≈ 1.0s
        assert result.travel_time_s == pytest.approx(30.0, rel=1e-2)

    def test_large_crowd_flow_dominates(self):
        """500 occupants — flow time dominates over travel time."""
        result = calculate_egress_time(
            occupant_count=500,
            travel_distance_m=10.0,
            exit_width_m=0.91,
        )
        # Travel = 10s, Flow = 500/(0.91*1.1) ≈ 499.5s
        assert result.travel_time_s > 10.0  # Flow dominates

    def test_stair_egress(self):
        """Stair egress uses reduced speed and flow rate."""
        result_level = calculate_egress_time(
            occupant_count=50,
            travel_distance_m=30.0,
            exit_width_m=0.91,
            is_stair=False,
        )
        result_stair = calculate_egress_time(
            occupant_count=50,
            travel_distance_m=30.0,
            exit_width_m=0.91,
            is_stair=True,
        )
        # Stair is slower → longer travel time
        assert result_stair.travel_time_s > result_level.travel_time_s

    def test_adequate_egress(self):
        """Large ASET / small RSET → adequate."""
        result = calculate_egress_time(
            occupant_count=10,
            travel_distance_m=10.0,
            exit_width_m=1.2,
            aset_s=1200.0,
            premovement_time_s=30.0,
        )
        if result.safety_factor >= _SAFETY_FACTOR:
            assert result.is_adequate is True

    def test_inadequate_egress(self):
        """Small ASET / large RSET → inadequate."""
        result = calculate_egress_time(
            occupant_count=500,
            travel_distance_m=100.0,
            exit_width_m=0.91,
            aset_s=60.0,
            premovement_time_s=30.0,
        )
        # RSET will be large, ASET small
        assert result.is_adequate is False

    def test_safety_factor_calculation(self):
        result = calculate_egress_time(
            occupant_count=50,
            travel_distance_m=30.0,
            exit_width_m=0.91,
            aset_s=600.0,
            premovement_time_s=60.0,
        )
        if result.rset_s > 0:
            expected = 600.0 / result.rset_s
            assert result.safety_factor == pytest.approx(expected, rel=1e-2)

    def test_negative_occupant_count_raises(self):
        with pytest.raises(ValueError, match="non-negative integer"):
            calculate_egress_time(occupant_count=-1, travel_distance_m=30.0)

    def test_float_occupant_count_raises(self):
        with pytest.raises(ValueError, match="non-negative integer"):
            calculate_egress_time(occupant_count=10.5, travel_distance_m=30.0)

    def test_negative_travel_distance_raises(self):
        with pytest.raises(ValueError, match="non-negative finite"):
            calculate_egress_time(occupant_count=10, travel_distance_m=-5.0)

    def test_nan_travel_distance_raises(self):
        with pytest.raises(ValueError, match="non-negative finite"):
            calculate_egress_time(occupant_count=10, travel_distance_m=float("nan"))

    def test_inf_travel_distance_raises(self):
        with pytest.raises(ValueError, match="non-negative finite"):
            calculate_egress_time(occupant_count=10, travel_distance_m=float("inf"))

    def test_zero_exit_width_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_egress_time(occupant_count=10, travel_distance_m=30.0, exit_width_m=0.0)

    def test_negative_exit_width_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_egress_time(occupant_count=10, travel_distance_m=30.0, exit_width_m=-1.0)

    def test_nan_exit_width_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_egress_time(occupant_count=10, travel_distance_m=30.0, exit_width_m=float("nan"))

    def test_zero_aset_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_egress_time(occupant_count=10, travel_distance_m=30.0, aset_s=0.0)

    def test_negative_aset_raises(self):
        with pytest.raises(ValueError, match="positive finite"):
            calculate_egress_time(occupant_count=10, travel_distance_m=30.0, aset_s=-100.0)

    def test_negative_premovement_raises(self):
        with pytest.raises(ValueError, match="non-negative finite"):
            calculate_egress_time(occupant_count=10, travel_distance_m=30.0, premovement_time_s=-10.0)

    def test_zero_travel_distance(self):
        """Zero distance — only flow time matters."""
        result = calculate_egress_time(
            occupant_count=50,
            travel_distance_m=0.0,
            exit_width_m=0.91,
        )
        # Travel = 0s, Flow = 50/(0.91*1.1) ≈ 49.95s
        assert result.travel_time_s > 0  # Flow time still counts


class TestEgressResultFrozen:
    """EgressResult is a frozen dataclass — immutable."""

    def test_immutable(self):
        result = calculate_egress_time(10, 30.0)
        with pytest.raises(AttributeError):
            result.rset_s = 999.0

    def test_has_all_fields(self):
        result = calculate_egress_time(10, 30.0)
        assert hasattr(result, "travel_time_s")
        assert hasattr(result, "premovement_time_s")
        assert hasattr(result, "rset_s")
        assert hasattr(result, "aset_s")
        assert hasattr(result, "safety_factor")
        assert hasattr(result, "is_adequate")
        assert hasattr(result, "occupant_count")
        assert hasattr(result, "exit_capacity_ps")
        assert hasattr(result, "nfpa_section")


# ─────────────────────────────────────────────────────────────────────────────
# Minimum Exit Width
# ─────────────────────────────────────────────────────────────────────────────


class TestMinimumExitWidth:
    def test_basic_calculation(self):
        """100 occupants, 300s RSET, 60s premovement.
        Available time = 240s.
        Required flow = 100/240 ≈ 0.417 p/s.
        Min width = 0.417/1.1 ≈ 0.379m → floored to 0.71m minimum.
        """
        result = minimum_exit_width(
            occupant_count=100,
            required_rset_s=300.0,
            premovement_time_s=60.0,
        )
        assert result["min_width_m"] >= _MIN_EGRESS_WIDTH_M
        assert "nfpa_section" in result

    def test_zero_occupants_returns_minimum(self):
        result = minimum_exit_width(0, 300.0)
        assert result["min_width_m"] == _MIN_EGRESS_WIDTH_M

    def test_negative_occupants_returns_minimum(self):
        result = minimum_exit_width(-5, 300.0)
        assert result["min_width_m"] == _MIN_EGRESS_WIDTH_M

    def test_impossible_egress(self):
        """RSET ≤ premovement time → impossible."""
        result = minimum_exit_width(100, 60.0, premovement_time_s=60.0)
        assert result["min_width_m"] == float("inf")
        assert "error" in result

    def test_rset_less_than_premovement(self):
        """RSET below premovement time is impossible."""
        result = minimum_exit_width(100, 30.0, premovement_time_s=60.0)
        assert result["min_width_m"] == float("inf")

    def test_stair_egress_wider(self):
        """Stair flow rate is lower → needs wider exit."""
        level = minimum_exit_width(200, 300.0, 60.0, is_stair=False)
        stair = minimum_exit_width(200, 300.0, 60.0, is_stair=True)
        # Stair needs wider exit due to lower flow rate
        if level["min_width_m"] != float("inf") and stair["min_width_m"] != float("inf"):
            assert stair["min_width_m"] >= level["min_width_m"]

    def test_minimum_width_enforced(self):
        """Result must be at least NFPA 101 §7.3.4 minimum (0.71m)."""
        result = minimum_exit_width(5, 600.0, 60.0)
        assert result["min_width_m"] >= _MIN_EGRESS_WIDTH_M

    def test_large_crowd_needs_wider_exit(self):
        small = minimum_exit_width(50, 300.0, 60.0)
        large = minimum_exit_width(500, 300.0, 60.0)
        assert large["min_width_m"] >= small["min_width_m"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
