"""
qomn_conduit — NFPA 72 Fire Alarm Conduit Fitting Engine
========================================================

Public API for conduit fill calculation, bend radius verification,
orthogonal pathfinding, fitting placement, and BIM output generation.

All functions return Result[T, E] — never raise in computation paths.

ENGINEERING SOURCES:
  NEC 2022 Chapter 9     — Conduit fill and area tables
  NEC 358 / 352 / 344    — EMT, PVC, RGD conduit standards
  NFPA 72-2022 §12.2     — Fire alarm circuit class and conduit requirements

Usage:
    from qomn_conduit import (
        ConduitType, TradeSize, FittingType, Point3D,
        calculate_fill, verify_bend_radius,
        orthogonal_astar, place_fittings,
        generate_revit_conduit, generate_schedules,
    )
"""

from qomn_conduit.types import (
    ConduitType,
    TradeSize,
    FittingType,
    Point3D,
    Result,
    FillResult,
    BendResult,
    RoutePath,
    ConduitRun,
    ConduitSegment,
    PlacedFitting,
)
from qomn_conduit.errors import (
    ConduitError,
    PhysicsError,
    CodeViolationError,
    CatalogError,
    RoutingError,
    Severity,
)
from qomn_conduit.catalog import (
    Fitting,
    get_fitting,
    catalog_size,
    all_fittings,
)
from qomn_conduit.fill import (
    calculate_fill,
    get_internal_area,
)
from qomn_conduit.bend import (
    verify_bend_radius,
    calculate_developed_length,
    verify_cumulative_bends,
    MAX_CUMULATIVE_BEND_DEG,
)
from qomn_conduit.router import (
    BoundingBox,
    ConduitRouter,
    orthogonal_astar,
)
from qomn_conduit.fitting_engine import place_fittings
from qomn_conduit.output import (
    generate_revit_conduit,
    generate_autocad_entities,
    generate_schedules,
)

__all__ = [
    # Types
    "ConduitType", "TradeSize", "FittingType", "Point3D", "Result",
    "FillResult", "BendResult", "RoutePath", "ConduitRun",
    "ConduitSegment", "PlacedFitting",
    # Errors
    "ConduitError", "PhysicsError", "CodeViolationError",
    "CatalogError", "RoutingError", "Severity",
    # Catalog
    "Fitting", "get_fitting", "catalog_size", "all_fittings",
    # Fill
    "calculate_fill", "get_internal_area",
    # Bend
    "verify_bend_radius", "calculate_developed_length",
    "verify_cumulative_bends", "MAX_CUMULATIVE_BEND_DEG",
    # Router
    "BoundingBox", "ConduitRouter", "orthogonal_astar",
    # Fitting engine
    "place_fittings",
    # Output
    "generate_revit_conduit", "generate_autocad_entities", "generate_schedules",
]

__version__ = "1.0.0"
