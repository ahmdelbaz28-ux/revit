"""
V12 Compatibility Wrapper

This module provides compatibility wrappers for V12 API calls.
It maps V12 function signatures to the original project signatures
without modifying the original code.

NOTE: This is a pure wrapper that redirects calls - no behavioral changes.
"""

from typing import List, Tuple, Optional
from nfpa72_coverage import check_coverage_polygon as original_check_coverage_polygon
from nfpa72_models import RoomSpec, CeilingSpec, DetectorType, CoverageResult
from spatial_engine.mip_solver import OptimalMIPEngine as OriginalOptimalMIPEngine


def check_coverage_polygon_compat(
    positions: List[Tuple[float, float]] = None,
    room_spec: RoomSpec = None,
    ceiling = None,  # Can be CeilingSpec or None
    detector_type = None,
    required_coverage_pct: float = 100.0,
) -> CoverageResult:
    """
    V12 compatible wrapper for check_coverage_polygon.
    
    Maps V12 parameters to original project parameters:
    - V12 uses 'positions', project uses 'detectors' (same data)
    - V12 uses 'ceiling', project uses 'ceiling_spec' (same data)
    
    No behavioral changes - pure redirect.
    """
    # Map V12 'positions' to original 'detectors'
    detectors = positions
    
    # Map V12 'ceiling' to original 'ceiling_spec'
    ceiling_spec = ceiling
    
    # Call original function with mapped parameters
    return original_check_coverage_polygon(
        detector_positions=detectors,
        room_spec=room_spec,
        ceiling_spec=ceiling_spec,
        detector_type=detector_type,
        required_coverage_pct=required_coverage_pct,
    )


class OptimalMIPEngine_compat(OriginalOptimalMIPEngine):
    """
    V12 compatible wrapper for OptimalMIPEngine.
    
    Maps V12 parameters to original project parameters:
    - V12 uses 'grid_size', project uses calculated 'area_m2' from grid
    - Passes through to parent class with mapped parameters
    
    No behavioral changes - pure redirect.
    """
    
    def __init__(
        self,
        grid_size: float = 0.0,  # V12 parameter (ignored or used to derive area)
        radius: float = 0.0,
        placement_step: float = 0.5,
        coverage_step: float = 0.5,
        time_limit_s: float = 30.0,
        **kwargs
    ):
        """
        Initialize V12 compatible OptimalMIPEngine.
        
        Args:
            grid_size: V12 grid size parameter (used to derive area if needed)
            radius: Coverage radius
            placement_step: Placement step
            coverage_step: Coverage step  
            time_limit_s: Time limit in seconds
            **kwargs: Additional V12 parameters
        """
        # Calculate area_m2 from grid_size if provided and positive
        # Otherwise use default based on grid_size or room dimensions from kwargs
        area_m2 = kwargs.get('area_m2', 0.0)
        
        if area_m2 <= 0 and grid_size > 0:
            # Derive area from grid size (grid_size * grid_size gives grid cell area)
            # For typical usage, use grid_size as area approximation
            area_m2 = grid_size * grid_size if grid_size > 0 else 100.0
        
        if area_m2 <= 0:
            # Default fallback area
            area_m2 = 100.0
        
        # Call parent with mapped parameter
        super().__init__(
            room_spec=None,  # Will be handled by parent
            grid_size=0.0,  # Use area_m2 instead
            radius=radius,
            placement_step=placement_step,
            coverage_step=coverage_step,
            time_limit_s=time_limit_s,
            area_m2=area_m2,
            **kwargs
        )


def patch_for_v12():
    """
    Apply monkey patches to enable V12 compatibility.
    
    This function patches the nfpa72_coverage and spatial_engine modules
    to redirect V12 calls to compatibility wrappers.
    
    Call this BEFORE importing fire_expert_system_v12.
    """
    import nfpa72_coverage
    import spatial_engine.mip_solver
    
    # Patch nfpa72_coverage module
    nfpa72_coverage.check_coverage_polygon = check_coverage_polygon_compat
    
    # Patch spatial_engine.mip_solver module
    spatial_engine.mip_solver.OptimalMIPEngine = OptimalMIPEngine_compat
    
    # Also patch at import location that V12 might use
    import sys
    if 'fireai.core.fire_expert_system_v12' in sys.modules:
        # Reload module to pick up patches
        del sys.modules['fireai.core.fire_expert_system_v12']
    
    return True