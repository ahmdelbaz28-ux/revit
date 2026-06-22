"""
ETAP-AI-WORK Revit Integration Mappings
======================================

Mapping engine for Revit categories to ETAP models.

Principal Software Architect: Eng. Ahmed Elbaz
"""
from .category_mapper import CategoryMapper

# Note: Other mappers (ElectricalEquipmentMapper, SpatialMapper, GeometryMapper) 
# are planned but not yet implemented
# from .electrical_mapper import ElectricalEquipmentMapper
# from .spatial_mapper import SpatialMapper
# from .geometry_mapper import GeometryMapper

__all__ = [
    'CategoryMapper',
    # 'ElectricalEquipmentMapper',
    # 'SpatialMapper', 
    # 'GeometryMapper'
]