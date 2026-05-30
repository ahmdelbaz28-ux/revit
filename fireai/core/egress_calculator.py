"""
fireai.core.egress_calculator — Egress Time Calculation per NFPA 101
=====================================================================

Implements egress time calculation for occupant evacuation:

1. Travel Time     — Mflow model per NFPA 101 §7.3
2. Flow Rate       — Door/corridor capacity per SFPE / NFPA 101
3. Available Safe Egress Time (ASET) vs Required Safe Egress Time (RSET)

SAFETY CRITICAL:
  - ASET > RSET is REQUIRED for life safety
  - If RSET ≥ ASET, occupants CANNOT evacuate safely
  - A safety margin (ASET/RSET ≥ 1.5) is applied per best practice
  - All calculations are engineering ESTIMATES
  - All NaN/Inf inputs are REJECTED

ENGINEERING SOURCES:
  - NFPA 101-2024 Chapter 7 — Means of Egress
  - NFPA 101 §7.3 — Capacity of Means of Egress
  - SFPE Handbook — Egress calculations
  - PD 7974-6 — Human factors in fire engineering
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

# Walking speed on level surface (m/s) — NFPA 101 / SFPE
_WALKING_SPEED_M_S = 1.0  # 1.0 m/s for normal adults

# Walking speed on stairs (m/s) — reduced for stair descent
_STAIR_SPEED_M_S = 0.5

# Flow rate per unit width (persons/m/s) — SFPE / NFPA 101
# Through doors: 1.1 persons/m/s per NFPA 101
_FLOW_RATE_DOOR_PER_M = 1.1

# Through corridors: 1.1 persons/m/s per SFPE
_FLOW_RATE_CORRIDOR_PER_M = 1.1

# Through stairs: 0.88 persons/m/s per SFPE
_FLOW_RATE_STAIR_PER_M = 0.88

# Minimum clear width for egress (m) — NFPA 101 §7.3.4
_MIN_EGRESS_WIDTH_M = 0.71  # 28 inches

# Safety factor: ASET/RSET must be ≥ this value
_SAFETY_FACTOR = 1.5

# Pre-movement time range (seconds) — PD 7974-6
_PREMOVEMENT_MIN_S = 30.0   # Alerted, trained occupants
_PREMOVEMENT_MAX_S = 180.0  # Sleeping occupants


@dataclass(frozen=True)
class EgressResult:
    """Result from egress time calculation.

    ASET/RSET Analysis:
      RSET = Detection Time + Pre-movement Time + Travel Time
      ASET = Time until conditions become untenable
      Safety Factor = ASET / RSET

    If Safety Factor < 1.5, the egress design may be inadequate.
    If Safety Factor < 1.0, occupants CANNOT evacuate safely.

    Fields:
        travel_time_s:      Time for last occupant to reach exit
        premovement_time_s:  Pre-movement / response time
        rset_s:             Required Safe Egress Time
        aset_s:             Available Safe Egress Time
        safety_factor:      ASET / RSET ratio
        is_adequate:        True if safety_factor ≥ 1.5
        occupant_count:     Number of occupants
        exit_capacity_ps:   Exit capacity (persons/second)
        nfpa_section:       NFPA 101 reference
    """
    travel_time_s:       float
    premovement_time_s:  float
    rset_s:              float
    aset_s:              float
    safety_factor:       float
    is_adequate:         bool
    occupant_count:      int
    exit_capacity_ps:    float
    nfpa_section:        str


def calculate_egress_time(
    occupant_count: int,
    travel_distance_m: float,
    exit_width_m: float = 0.91,
    aset_s: float = 600.0,
    premovement_time_s: float = 60.0,
    is_stair: bool = False,
) -> EgressResult:
    """Calculate Required Safe Egress Time (RSET) per NFPA 101 §7.3.

    NFPA 101 Chapter 7 — Egress Time Components:
      1. Travel Time: distance / walking speed
      2. Flow Time: occupants / (exit_width × flow_rate)
      3. Pre-movement Time: occupant response time
      4. RSET = max(Travel, Flow) + Pre-movement

    The travel time and flow time run concurrently — the total
    evacuation time is the maximum of these two, plus pre-movement.

    Args:
        occupant_count: Number of occupants to evacuate.
        travel_distance_m: Travel distance to nearest exit in meters.
        exit_width_m: Clear exit width in meters (default 0.91m = 36in).
        aset_s: Available Safe Egress Time in seconds.
        premovement_time_s: Pre-movement time in seconds.
        is_stair: If True, uses stair speed and flow rate.

    Returns:
        EgressResult with RSET, ASET, safety factor, and adequacy.
    """
    # Input validation
    if not isinstance(occupant_count, int) or occupant_count < 0:
        raise ValueError(f"occupant_count must be non-negative integer, got {occupant_count}")
    if not math.isfinite(travel_distance_m) or travel_distance_m < 0:
        raise ValueError(f"travel_distance_m must be non-negative finite, got {travel_distance_m}")
    if not math.isfinite(exit_width_m) or exit_width_m <= 0:
        raise ValueError(f"exit_width_m must be positive finite, got {exit_width_m}")
    if not math.isfinite(aset_s) or aset_s <= 0:
        raise ValueError(f"aset_s must be positive finite, got {aset_s}")
    if not math.isfinite(premovement_time_s) or premovement_time_s < 0:
        raise ValueError(f"premovement_time_s must be non-negative finite, got {premovement_time_s}")

    # Edge case: no occupants
    if occupant_count == 0:
        return EgressResult(
            travel_time_s=0.0,
            premovement_time_s=0.0,
            rset_s=0.0,
            aset_s=aset_s,
            safety_factor=float('inf'),
            is_adequate=True,
            occupant_count=0,
            exit_capacity_ps=0.0,
            nfpa_section="NFPA 101 §7.3",
        )

    # Walking speed
    speed = _STAIR_SPEED_M_S if is_stair else _WALKING_SPEED_M_S
    flow_rate = _FLOW_RATE_STAIR_PER_M if is_stair else _FLOW_RATE_DOOR_PER_M

    # Travel time: time for one person to walk to exit
    travel_time = travel_distance_m / speed

    # Exit capacity (persons/second)
    exit_capacity = exit_width_m * flow_rate

    # Flow time: time for all occupants to pass through exit
    flow_time = occupant_count / max(exit_capacity, 0.01)

    # Total travel time is the max of individual travel and flow
    total_travel = max(travel_time, flow_time)

    # RSET = Pre-movement + Travel
    rset = premovement_time_s + total_travel

    # Safety factor
    if rset > 0:
        safety_factor = aset_s / rset
    else:
        safety_factor = float('inf')

    is_adequate = safety_factor >= _SAFETY_FACTOR

    return EgressResult(
        travel_time_s=round(total_travel, 2),
        premovement_time_s=premovement_time_s,
        rset_s=round(rset, 2),
        aset_s=aset_s,
        safety_factor=round(safety_factor, 4),
        is_adequate=is_adequate,
        occupant_count=occupant_count,
        exit_capacity_ps=round(exit_capacity, 4),
        nfpa_section="NFPA 101 §7.3",
    )


def minimum_exit_width(
    occupant_count: int,
    required_rset_s: float,
    premovement_time_s: float = 60.0,
    is_stair: bool = False,
) -> Dict[str, Any]:
    """Calculate minimum exit width for a given RSET requirement.

    NFPA 101 §7.3 — Egress capacity:
      Required flow = occupants / (RSET - premovement)
      Required width = required_flow / flow_rate_per_m

    Args:
        occupant_count: Number of occupants.
        required_rset_s: Maximum allowed RSET in seconds.
        premovement_time_s: Pre-movement time in seconds.
        is_stair: If True, uses stair flow rate.

    Returns:
        Dict with min_width_m, flow_rate, and NFPA reference.
    """
    if occupant_count <= 0:
        return {"min_width_m": _MIN_EGRESS_WIDTH_M, "nfpa_section": "NFPA 101 §7.3.4"}

    available_time = required_rset_s - premovement_time_s
    if available_time <= 0:
        return {
            "min_width_m": float('inf'),
            "error": "RSET ≤ premovement time — impossible egress",
            "nfpa_section": "NFPA 101 §7.3",
        }

    flow_rate = _FLOW_RATE_STAIR_PER_M if is_stair else _FLOW_RATE_DOOR_PER_M
    required_flow = occupant_count / available_time
    min_width = required_flow / flow_rate

    # Enforce minimum egress width per NFPA 101
    min_width = max(min_width, _MIN_EGRESS_WIDTH_M)

    return {
        "min_width_m": round(min_width, 4),
        "required_flow_ps": round(required_flow, 4),
        "flow_rate_per_m": flow_rate,
        "nfpa_section": "NFPA 101 §7.3",
    }
