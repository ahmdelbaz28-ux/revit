"""
NFPA72ConstraintProvider — Pure Domain Layer
============================================
Layer 1 (Domain). Knows NFPA 72 tables. Knows NOTHING else.
Zero imports from project. Only Python stdlib.

NFPA 72 2025 Table 17.6.3.1 — detector spacing on smooth ceilings
"""

from typing import Dict


class NFPA72ConstraintProvider:
    """
    Pure domain provider for NFPA 72 constraint values.
    No dependencies on any other layer.
    """
    
    # NFPA 72 2025 Table 17.6.3.1 — detector spacing on smooth ceilings
    SPACING = {
        "SMOKE_PHOTOELECTRIC": 9.1,   # 30 ft = 9.144m → 9.1m
        "SMOKE_IONIZATION": 9.1,
        "HEAT_FIXED": 6.1,            # 20 ft = 6.096m → 6.1m
        "HEAT_RATE_OF_RISE": 15.2,      # 50 ft = 15.24m → 15.2m (listed spacing)
        "MULTI_CRITERIA": 9.1,
        # Fallback
        "DEFAULT": 9.1,
    }
    
    # Minimum spacing between detectors (NFPA 72 17.7.3.1)
    MIN_DETECTOR_SPACING = {
        "SMOKE_PHOTOELECTRIC": 3.0,   # 10 ft minimum
        "SMOKE_IONIZATION": 3.0,
        "HEAT_FIXED": 3.0,
        "HEAT_RATE_OF_RISE": 3.0,
        "MULTI_CRITERIA": 3.0,
        "DEFAULT": 3.0,
    }
    
    @staticmethod
    def get_spacing(device_type: str) -> float:
        """Get base spacing from table (in meters)."""
        return NFPA72ConstraintProvider.SPACING.get(
            device_type, 
            NFPA72ConstraintProvider.SPACING["DEFAULT"]
        )
    
    @staticmethod
    def get_minimum_spacing(device_type: str) -> float:
        """Get minimum detector-to-detector spacing (in meters)."""
        return NFPA72ConstraintProvider.MIN_DETECTOR_SPACING.get(
            device_type,
            NFPA72ConstraintProvider.MIN_DETECTOR_SPACING["DEFAULT"]
        )
    
    @staticmethod
    def get_effective_radius(
        device_type: str, 
        ceiling_height: float = 2.8,
        ceiling_type: str = "SMOOTH"
    ) -> float:
        """
        Calculate effective coverage radius with corrections.
        
        NFPA 72 adjustments:
        - Smoke detectors: stratify above 3.0m ceiling height
        - Beamed ceilings: reduce coverage due to obstruction
        - Coverage radius = base_spacing * 0.7 (per NFPA 72)
        
        Args:
            device_type: Device type from SPACING keys
            ceiling_height: Ceiling height in meters (default 2.8m)
            ceiling_type: "SMOOTH" or "BEAMED"
        
        Returns:
            Effective coverage radius in meters
        """
        base_spacing = NFPA72ConstraintProvider.get_spacing(device_type)
        
        # Coverage radius per NFPA 72 = 70% of listed spacing
        radius = base_spacing * 0.7
        
        # Heat detector stratification correction (above 3.0m) per NFPA 72 Table 17.6.3.5.1
        # NOTE: Smoke detectors maintain full spacing up to 12.2m (40ft) per NFPA 72
        if ceiling_height > 3.0 and device_type in ["HEAT_FIXED", "HEAT_RATE_OF_RISE"]:
            # Each 0.3m above 3.0m reduces coverage by ~2%
            height_over = ceiling_height - 3.0
            reduction = min(0.15, (height_over / 0.3) * 0.02)  # Max 15%
            radius *= (1 - reduction)
        # Smoke detectors: NO reduction up to 12.2m (40ft) per NFPA 72
        # If > 12.2m, keep base radius - Oracle will warn engineer
        
        # Beam obstruction correction
        if ceiling_type == "BEAMED":
            radius *= 0.80  # 20% reduction per NFPA 72
        
        return round(radius, 2)