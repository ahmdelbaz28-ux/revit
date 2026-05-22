"""
Multi-Floor Fire Alarm System Analyzer
================================
Handles multi-story buildings, floor-by-floor panels, addressable loops.

MISSING: This requires professional engineering design!
"""

from dataclasses import dataclass
from typing import List, Dict, Optional
from enum import Enum


class PanelType(Enum):
    """Fire alarm panel types."""
    CONVENTIONAL = "conventional"      # 2-wire, zones
    ADDRESSABLE = "addressable"        # SLC loop
    NETWORK = "network"              # Multiple panels


class FloorInfo:
    """Information about each floor.
    
    Usage:
        FloorInfo(level=1, area=500, devices=45)
    """
    def __init__(self, level: int = 1, area: float = 500, devices: int = 0):
        self.floor_number = level
        self.floor_area = area
        self.devices_count = devices
        self.panel_recommended = False


class MultiFloorAnalyzer:
    """
    Analyzer for multi-story buildings.
    
    Usage:
        floors = [FloorInfo(level=1, area=500, devices=45)]
        result = MultiFloorAnalyzer.analyze_building(floors, max_devices_per_panel=1000)
    """
    
    # NFPA 72 limits per panel
    MAX_CONVENTIONAL_ZONES = 99
    MAX_ADDRESSABLE_DEVICES = 250  # Per loop
    MAX_DEVICES_PER_PANEL = 500
    
    # Maximum wire run (approximate)
    MAX_WIRE_LENGTH = {
        "conventional_14awg": 300,   # meters (5000ft for #14)
        "addressable_loop": 1500,     # meters (SLC)
        "network_fiber": 3000,         # meters (fiber)
    }
    
    @classmethod
    def analyze_building(
        cls,
        floors: List[FloorInfo],
        max_devices_per_panel: int = 500,
        panel_type: str = "addressable"
    ) -> Dict:
        """
        Analyze multi-floor building.
        
        Returns recommendation for panels per floor.
        """
        total_devices = sum(f.devices_count for f in floors)
        
        # Check if single panel is sufficient
        if max_devices_per_panel and total_devices <= max_devices_per_panel:
            return {
                "panels_needed": 1,
                "panel_type": panel_type,
                "devices_per_panel": total_devices,
                "recommendation": "Single panel may be sufficient"
            }
        
        # Multiple panels needed
        import math
        panels_needed = math.ceil(total_devices / cls.MAX_DEVICES_PER_PANEL)
        
        return {
            "panels_needed": panels_needed,
            "panel_type": panel_type,
            "devices_per_panel": math.ceil(total_devices / panels_needed),
            "recommendation": f"{panels_needed} panels recommended"
        }
    
    @classmethod
    def check_multi_building(
        cls,
        building_positions: List[tuple],
        max_distance: float = 150  # meters
    ) -> Dict:
        """
        Check if buildings can be served by single panel/network.
        
        ⚠️  This is APPROXIMATE - requires engineering!
        """
        if len(building_positions) <= 1:
            return {
                "single_panel": True, 
                "reason": "Single building",
                "recommendation": "Single panel OK"
            }
        
        # Calculate distances between buildings
        import math
        max_dist = 0
        for i, pos1 in enumerate(building_positions):
            for pos2 in building_positions[i+1:]:
                d = math.sqrt((pos1[0]-pos2[0])**2 + (pos1[1]-pos2[1])**2)
                max_dist = max(max_dist, d)
        
        if max_dist > max_distance:
            return {
                "single_panel": False,
                "reason": f"Distance {max_dist:.0f}m exceeds limit",
                "recommendation": "Multiple panels or fiber network required"
            }
        
        return {
            "single_panel": True,
            "reason": f"Max distance {max_dist:.0f}m within limit",
            "recommendation": "Fiber network recommended for reliability"
        }


# Simple cable calculation
def calculate_cable_length(
    start: tuple,
    end: tuple,
    routing_factor: float = 1.15  # 15% for bends/path
) -> float:
    """
    Calculate approximate cable length.
    
    ⚠️  APPROXIMATE - actual requires path tracing!
    
    V20.2 FIX: Now supports 3D coordinates. Previous code used 2D only,
    severely underestimating cable length for multi-floor runs. A cable
    from floor 1 to floor 5 with 4m floor-to-floor height would have
    its length underestimated by ~16m, causing voltage drop calculations
    to be wrong — horns/strobes may not operate during fire.
    """
    import math
    # V20.2: Use 3D distance when Z coordinates are available
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    dz = (end[2] - start[2]) if len(start) > 2 and len(end) > 2 else 0.0
    direct = math.sqrt(dx*dx + dy*dy + dz*dz)
    return direct * routing_factor


def estimate_voltage_drop(
    distance: float,
    current: float,
    wire_gauge: int = 14  # AWG
) -> float:
    """
    Exact DC voltage drop calculation for fire alarm circuits.

    CRITICAL: DC circuits (NAC / SLC) require the return path to be
    accounted for. Current flows out on one conductor and returns on
    another, so the total wire length is 2x the one-way distance.

    Failure to multiply by 2 under-reports voltage drop by 50%, which
    can leave notification appliances (horns/strobes) at the end of the
    line without enough voltage to operate during a fire — a life-safety
    failure per NEC 760 and NFPA 72 Chapter 10.

    Parameters
    ----------
    distance : float
        One-way distance in metres.
    current : float
        Circuit current in amperes.
    wire_gauge : int
        AWG wire size (14, 12, 10, 8).

    Returns
    -------
    float
        Voltage drop in volts (out + return).
    """
    # Resistance per 1000 ft (NEC Chapter 9, Table 8 — copper)
    resistance = {
        14: 3.0,   # Ω/kft
        12: 1.9,
        10: 1.2,
        8: 0.75,
    }.get(wire_gauge, 3.0)

    # Convert one-way metres to feet
    length_ft = distance * 3.281

    # V_drop = 2 × I × R × (L / 1000)
    # The factor of 2 accounts for the DC return path (out and back).
    vdrop = 2.0 * current * resistance * (length_ft / 1000.0)

    return vdrop


print("Multi-floor analyzer loaded - SIMPLIFIED MODEL")
print("⚠️  WARNING: Do NOT use for actual installations!")