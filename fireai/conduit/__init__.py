"""fireai.conduit — NFPA 72 Fire Alarm Conduit Fitting Engine
===========================================================

Public API for conduit fill calculation, bend radius verification,
orthogonal pathfinding, fitting placement, and BIM output generation.

All functions return Result[T, E] — never raise in computation paths.

ENGINEERING SOURCES:
  NEC 2022 Chapter 9     — Conduit fill and area tables
  NEC 358 / 352 / 344    — EMT, PVC, RGD conduit standards
  NFPA 72-2022 §12.2     — Fire alarm circuit class and conduit requirements

Usage:
    from fireai.conduit import (
        ConduitType, TradeSize, FittingType, Point3D,
        calculate_fill, verify_bend_radius,
        orthogonal_astar, place_fittings,
        generate_revit_conduit, generate_schedules,
    )
"""

from fireai.conduit.bend import (
    MAX_CUMULATIVE_BEND_DEG,
    calculate_developed_length,
    verify_bend_radius,
    verify_cumulative_bends,
)
from fireai.conduit.catalog import (
    Fitting,
    all_fittings,
    catalog_size,
    get_fitting,
)
from fireai.conduit.errors import (
    CatalogError,
    CodeViolationError,
    ConduitError,
    PhysicsError,
    RoutingError,
    Severity,
)
from fireai.conduit.fill import (
    calculate_fill,
    calculate_fill_compliant,
    get_internal_area,
)
from fireai.conduit.fitting_engine import place_fittings
from fireai.conduit.output import (
    generate_autocad_entities,
    generate_revit_conduit,
    generate_schedules,
)
from fireai.conduit.router import (
    BoundingBox,
    ConduitRouter,
    orthogonal_astar,
)
from fireai.conduit.types import (
    BendResult,
    ConduitRun,
    ConduitSegment,
    ConduitType,
    FillResult,
    FittingType,
    PlacedFitting,
    Point3D,
    Result,
    RoutePath,
    TradeSize,
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
    "calculate_fill", "calculate_fill_compliant", "get_internal_area",
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
