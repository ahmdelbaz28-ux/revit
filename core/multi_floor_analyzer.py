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


@dataclass
class FloorInfo:
    """Information about each floor."""
    floor_number: int
    floor_area: float  # m²
    devices_count: int
    panel_recommended: bool = False


class MultiFloorAnalyzer:
    """
    Analyzer for multi-story buildings.
    
    ⚠️  WARNING: This is a SIMPLIFIED model!
    Actual design requires professional engineer.
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
        building_area: float,
        panel_type: str = "addressable"
    ) -> Dict:
        """
        Analyze multi-floor building.
        
        Returns recommendation for panels per floor.
        """
        total_devices = sum(f.devices_count for f in floors)
        
        # Check if single panel is sufficient
        if total_devices <= cls.MAX_DEVICES_PER_PANEL:
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
        max_single_building: float = 150  # meters
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
        
        if max_dist > max_single_building:
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
    """
    import math
    direct = math.sqrt((start[0]-end[0])**2 + (start[1]-end[1])**2)
    return direct * routing_factor


def estimate_voltage_drop(
    length_meters: float,
    current_amps: float,
    wire_gauge: int = 14  # AWG
) -> float:
    """
    Estimate voltage drop (simplified).
    
    ⚠️  APPROXIMATE - requires actual calculation!
    
    Returns: voltage drop in volts
    """
    # Resistance per 1000ft (approximate)
    resistance = {
        14: 3.0,
        12: 1.9,
        10: 1.2,
        8: 0.75,
    }.get(wire_gauge, 3.0)
    
    # Convert meters to feet
    length_ft = length_meters * 3.281
    
    # Calculate drop: V = I × R × (L/1000)
    vdrop = current_amps * resistance * (length_ft / 1000)
    
    return vdrop


print("Multi-floor analyzer loaded - SIMPLIFIED MODEL")
print("⚠️  WARNING: Do NOT use for actual installations!")