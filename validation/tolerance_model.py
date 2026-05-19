"""
Validation Layer - Tolerance Model
============================
Defines tolerance thresholds for geometric operations.
"""

from dataclasses import dataclass


@dataclass
class ToleranceModel:
    """Tolerance thresholds for spatial normalization"""
    linear_epsilon: float = 1e-6       # threshold for coordinate equality
    area_epsilon: float = 1e-8         # threshold for zero-area geometries
    unit_scale_factor: float = 1.0     # 1.0 = meters, will be set by coercion
    max_repair_attempts: int = 3
    
    def __post_init__(self):
        # Ensure positive values
        if self.linear_epsilon <= 0:
            self.linear_epsilon = 1e-6
        if self.area_epsilon <= 0:
            self.area_epsilon = 1e-8
        if self.max_repair_attempts <= 0:
            self.max_repair_attempts = 3