"""
Validation Layer
==============
Provides geometric normalization and validation for BIM/CAD inputs.
"""

from validation.tolerance_model import ToleranceModel
from validation.unit_coercion import coerce_units
from validation.geometry_repair import (
    repair_polygon,
    repair_self_intersection,
    repair_duplicate_points,
    is_degenerate,
    is_valid_polygon
)
from validation.spatial_normalizer import SpatialNormalizer, GeometryError, ErrorSeverity

__all__ = [
    'ToleranceModel',
    'coerce_units',
    'repair_polygon',
    'repair_self_intersection',
    'repair_duplicate_points',
    'is_degenerate',
    'is_valid_polygon',
    'SpatialNormalizer',
    'GeometryError',
    'ErrorSeverity',
]