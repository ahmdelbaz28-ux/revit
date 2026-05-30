"""
fireai.core.spatial_engine — Spatial Optimization Engines
==========================================================

Provides density-based detector placement optimization and exact
coverage verification using Shapely geometric operations.

Modules:
  - density_optimizer: Greedy farthest-point detector placement
  - exact_coverage: Shapely-based exact coverage calculation
"""

from fireai.core.spatial_engine.density_optimizer import DensityOptimizer
from fireai.core.spatial_engine.exact_coverage import ExactCoverageEngine

__all__ = ["DensityOptimizer", "ExactCoverageEngine"]
