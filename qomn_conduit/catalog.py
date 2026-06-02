"""
qomn_conduit.catalog — Safety-Critical Conduit Fitting Catalog
==============================================================

Immutable catalog of conduit fittings for fire alarm system routing.

This module is the SINGLE SOURCE OF TRUTH for all fitting dimensions.
Every value is traceable to a specific NEC article. No computed or
estimated values are used for dimensions that are specified by code.

CATALOG STRUCTURE
-----------------
Fittings are stored as frozen dataclasses in two module-level dictionaries:

  _CATALOG : Dict[str, Fitting]
      Primary store keyed by catalog_number. Contains every registered
      fitting. Use ``all_fittings()`` to obtain a copy.

  _INDEX : Dict[Tuple[ConduitType, TradeSize, FittingType], str]
      Lookup index mapping (conduit_type, trade_size, fitting_type)
      to a catalog_number. Used by ``get_fitting()``.

NOTE — EMT has two coupling subtypes (compression and set-screw).
Both are stored in _CATALOG. The _INDEX maps (EMT, size, COUPLING)
to the compression coupling (EMT-C) as the default. Set-screw
couplings are retrievable by catalog number via ``all_fittings()``.

ENGINEERING SOURCES
-------------------
  NEC 2022 Article 358   — Electrical Metallic Tubing (EMT)
  NEC 2022 Article 352   — Rigid Nonmetallic Conduit (UPVC Sch 40/80)
  NEC 2022 Article 344   — Rigid Metal Conduit (RGD / RMC)
  NEC 2022 Chapter 9     — Conduit fill and bend radius tables
  NFPA 72-2022 §12.2     — Fire alarm circuit class requirements

SAFETY
------
This catalog supports life-safety fire alarm circuits (NFPA 72 Class A/B).
Incorrect dimensions can cause:
  - Exceeding NEC 360° cumulative bend limit → conductor damage on pull
  - Violating minimum bend radius → insulation damage → ground fault
  - Wrong coupling length → unsupported conduit span → physical damage

Every fitting entry is validated on construction. Physically impossible
values raise PhysicsError (FATAL). Missing catalog entries return
Result.err(CatalogError) — never raise.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Tuple

from qomn_conduit.errors import CatalogError, PhysicsError
from qomn_conduit.types import ConduitType, FittingType, Result, TradeSize


# ─────────────────────────────────────────────────────────────────────────────
# Fitting — immutable catalog entry
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Fitting:
    """
    A single conduit fitting entry in the safety-critical catalog.

    Frozen (immutable) to prevent accidental mutation after registration.
    All physical dimensions are in inches (consistent with NEC tables).

    Attributes:
        fitting_type:       Type of fitting (ELBOW_90, COUPLING, etc.).
        conduit_type:       NEC conduit material designation.
        trade_size:         Nominal trade size (1/2", 3/4", 1", etc.).
        od_in:              Outside diameter in inches (NEC Chapter 9, Table 4).
        bend_radius_in:     Centreline bend radius in inches.
                            0.0 for straight fittings (couplings, tees).
        developed_length_in: Arc length of bend in inches.
                            For 90° elbows: round(π × R / 2, 3).
                            0.0 for straight fittings.
        body_length_in:     Straight body length in inches.
                            0.0 for bent fittings (elbows).
        angle_deg:          Bend angle in degrees (90.0 or 45.0 for elbows,
                            0.0 for straight fittings).
        catalog_number:     Manufacturer catalog reference (e.g. 'E90-050').
        weight_kg:          Fitting weight in kilograms (0.0 if unlisted).
        nec_reference:      NEC article citation for this fitting's dimensions.

    Validation (__post_init__):
        - Elbows: bend_radius > 0, developed_length > 0, body_length == 0
        - Couplings: bend_radius == 0, developed_length == 0, body_length > 0,
          angle == 0
        - All: od > 0, weight >= 0, catalog_number non-empty
    """

    fitting_type: FittingType
    conduit_type: ConduitType
    trade_size: TradeSize
    od_in: float
    bend_radius_in: float
    developed_length_in: float
    body_length_in: float
    angle_deg: float
    catalog_number: str
    weight_kg: float
    nec_reference: str

    def __post_init__(self) -> None:
        """Validate physical consistency of catalog entry.

        Raises PhysicsError (FATAL) if any value violates physical laws
        or is inconsistent with the fitting type. This catches catalog
        data corruption or programmer errors at import time.
        """
        # ── Universal checks ───────────────────────────────────────
        if not self.catalog_number:
            raise PhysicsError(
                "Fitting catalog_number must be non-empty.",
                "Provide a valid manufacturer catalog number.",
            )
        if self.od_in <= 0.0:
            raise PhysicsError(
                f"Fitting {self.catalog_number}: od_in must be positive, "
                f"got {self.od_in}.",
                "Check catalog data for typos or corrupted OD values.",
            )
        if self.weight_kg < 0.0:
            raise PhysicsError(
                f"Fitting {self.catalog_number}: weight_kg must be "
                f"non-negative, got {self.weight_kg}.",
                "Check catalog data for weight values.",
            )

        # ── Elbow-specific checks ──────────────────────────────────
        if self.fitting_type in (FittingType.ELBOW_90, FittingType.ELBOW_45):
            if self.bend_radius_in <= 0.0:
                raise PhysicsError(
                    f"Fitting {self.catalog_number}: bend_radius_in must be "
                    f"positive for elbows, got {self.bend_radius_in}.",
                    "Check catalog data for bend radius values.",
                )
            if self.developed_length_in <= 0.0:
                raise PhysicsError(
                    f"Fitting {self.catalog_number}: developed_length_in must "
                    f"be positive for elbows, got {self.developed_length_in}.",
                    "Check catalog data or computation of developed length.",
                )
            if self.body_length_in != 0.0:
                raise PhysicsError(
                    f"Fitting {self.catalog_number}: body_length_in must be "
                    f"0.0 for elbows, got {self.body_length_in}.",
                    "Elbows use developed_length_in, not body_length_in.",
                )

        # ── Coupling-specific checks ───────────────────────────────
        if self.fitting_type == FittingType.COUPLING:
            if self.bend_radius_in != 0.0:
                raise PhysicsError(
                    f"Fitting {self.catalog_number}: bend_radius_in must be "
                    f"0.0 for couplings, got {self.bend_radius_in}.",
                    "Couplings are straight fittings with no bend.",
                )
            if self.developed_length_in != 0.0:
                raise PhysicsError(
                    f"Fitting {self.catalog_number}: developed_length_in must "
                    f"be 0.0 for couplings, got {self.developed_length_in}.",
                    "Couplings use body_length_in, not developed_length_in.",
                )
            if self.body_length_in <= 0.0:
                raise PhysicsError(
                    f"Fitting {self.catalog_number}: body_length_in must be "
                    f"positive for couplings, got {self.body_length_in}.",
                    "Check catalog data for coupling body length.",
                )
            if self.angle_deg != 0.0:
                raise PhysicsError(
                    f"Fitting {self.catalog_number}: angle_deg must be 0.0 "
                    f"for couplings, got {self.angle_deg}.",
                    "Couplings are straight fittings with no bend angle.",
                )

    def __repr__(self) -> str:
        return (
            f"Fitting({self.catalog_number!r} "
            f"{self.conduit_type.name} {self.trade_size.value} "
            f"{self.fitting_type.name})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Module-level catalog storage
# ─────────────────────────────────────────────────────────────────────────────

_CATALOG: Dict[str, Fitting] = {}
"""
Primary catalog store: catalog_number → Fitting.

Contains every registered fitting. Keyed by catalog_number because
it is the unique manufacturer identifier. Multiple fittings of the
same (conduit_type, trade_size, fitting_type) may exist (e.g. EMT
compression and set-screw couplings share the same key tuple but
have different catalog numbers).
"""

_INDEX: Dict[Tuple[ConduitType, TradeSize, FittingType], str] = {}
"""
Lookup index: (conduit_type, trade_size, fitting_type) → catalog_number.

Used by get_fitting() for O(1) lookup. Where multiple catalog entries
share the same key tuple (e.g. EMT-C and EMT-S couplings), the first
registered entry wins. EMT compression couplings (EMT-C) are registered
before set-screw (EMT-S) so that get_fitting() returns the compression
type by default.
"""


# ─────────────────────────────────────────────────────────────────────────────
# _reg — registration helper
# ─────────────────────────────────────────────────────────────────────────────

def _reg(
    fitting_type: FittingType,
    conduit_type: ConduitType,
    trade_size: TradeSize,
    od_in: float,
    bend_radius_in: float,
    body_length_in: float,
    angle_deg: float,
    catalog_number: str,
    weight_kg: float,
    nec_reference: str,
) -> None:
    """Register a fitting into the module-level catalog.

    For elbow fittings, ``developed_length_in`` is computed from the
    bend radius using the formula:

        90° elbow:  round(π × R / 2, 3)
        45° elbow:  round(π × R / 4, 3)
        General:    round(π × R × angle / 180, 3)

    This ensures the developed length is always consistent with the
    bend radius, eliminating a common source of catalog data errors.

    Args:
        fitting_type:   Type of fitting (ELBOW_90, COUPLING, etc.).
        conduit_type:   NEC conduit material designation.
        trade_size:     Nominal trade size.
        od_in:          Outside diameter in inches.
        bend_radius_in: Bend radius in inches (0.0 for couplings).
        body_length_in: Body length in inches (0.0 for elbows).
        angle_deg:      Bend angle in degrees (0.0 for couplings).
        catalog_number: Unique manufacturer catalog identifier.
        weight_kg:      Weight in kilograms (0.0 if unlisted).
        nec_reference:  NEC article citation string.

    Raises:
        PhysicsError: If the constructed Fitting fails __post_init__
                      validation (e.g. negative dimensions, inconsistent
                      values for the fitting type).
    """
    # Compute developed length for elbows; 0.0 for straight fittings.
    if fitting_type in (FittingType.ELBOW_90, FittingType.ELBOW_45):
        if angle_deg == 90.0:
            developed_length_in = round(math.pi * bend_radius_in / 2, 3)
        elif angle_deg == 45.0:
            developed_length_in = round(math.pi * bend_radius_in / 4, 3)
        else:
            developed_length_in = round(
                math.pi * bend_radius_in * angle_deg / 180.0, 3
            )
    else:
        developed_length_in = 0.0

    fitting = Fitting(
        fitting_type=fitting_type,
        conduit_type=conduit_type,
        trade_size=trade_size,
        od_in=od_in,
        bend_radius_in=bend_radius_in,
        developed_length_in=developed_length_in,
        body_length_in=body_length_in,
        angle_deg=angle_deg,
        catalog_number=catalog_number,
        weight_kg=weight_kg,
        nec_reference=nec_reference,
    )

    _CATALOG[catalog_number] = fitting

    key = (conduit_type, trade_size, fitting_type)
    if key not in _INDEX:
        _INDEX[key] = catalog_number


# ─────────────────────────────────────────────────────────────────────────────
# EMT ELBOW 90° STANDARD — NEC 358.24
# ─────────────────────────────────────────────────────────────────────────────
# NEC 358.24 requires that bends in EMT be made with a radius not less
# than six times the internal diameter. The values below are standard
# factory elbow dimensions from NEC Chapter 9, Table 4 and
# manufacturer data.
#
# Developed length = round(π × R / 2, 3) for 90° elbows.

_reg(FittingType.ELBOW_90, ConduitType.EMT, TradeSize.HALF_INCH,
     0.706, 4.0, 0.0, 90.0, "E90-050", 0.045, "NEC 358.24")

_reg(FittingType.ELBOW_90, ConduitType.EMT, TradeSize.THREE_QUARTER,
     0.922, 4.5, 0.0, 90.0, "E90-075", 0.068, "NEC 358.24")

_reg(FittingType.ELBOW_90, ConduitType.EMT, TradeSize.ONE_INCH,
     1.163, 5.75, 0.0, 90.0, "E90-100", 0.113, "NEC 358.24")

_reg(FittingType.ELBOW_90, ConduitType.EMT, TradeSize.ONE_QUARTER,
     1.510, 7.25, 0.0, 90.0, "E90-125", 0.181, "NEC 358.24")

_reg(FittingType.ELBOW_90, ConduitType.EMT, TradeSize.ONE_HALF,
     1.740, 8.25, 0.0, 90.0, "E90-150", 0.249, "NEC 358.24")

_reg(FittingType.ELBOW_90, ConduitType.EMT, TradeSize.TWO_INCH,
     2.197, 9.5, 0.0, 90.0, "E90-200", 0.408, "NEC 358.24")


# ─────────────────────────────────────────────────────────────────────────────
# UPVC SCH 40 ELBOW 90° — NEC 352.24
# ─────────────────────────────────────────────────────────────────────────────
# NEC 352.24 requires that PVC conduit bends maintain the cross-section
# throughout the bend. Schedule 40 is the standard wall thickness for
# Rigid Nonmetallic Conduit.
#
# OD and bend radius from NEC Chapter 9, Table 4 (RNC Schedule 40).

_reg(FittingType.ELBOW_90, ConduitType.UPVC_SCH40, TradeSize.HALF_INCH,
     0.840, 4.5, 0.0, 90.0, "P90-050", 0.038, "NEC 352.24")

_reg(FittingType.ELBOW_90, ConduitType.UPVC_SCH40, TradeSize.THREE_QUARTER,
     1.050, 5.25, 0.0, 90.0, "P90-075", 0.059, "NEC 352.24")

_reg(FittingType.ELBOW_90, ConduitType.UPVC_SCH40, TradeSize.ONE_INCH,
     1.315, 6.5, 0.0, 90.0, "P90-100", 0.091, "NEC 352.24")

_reg(FittingType.ELBOW_90, ConduitType.UPVC_SCH40, TradeSize.ONE_QUARTER,
     1.660, 8.0, 0.0, 90.0, "P90-125", 0.145, "NEC 352.24")

_reg(FittingType.ELBOW_90, ConduitType.UPVC_SCH40, TradeSize.ONE_HALF,
     1.900, 9.0, 0.0, 90.0, "P90-150", 0.190, "NEC 352.24")

_reg(FittingType.ELBOW_90, ConduitType.UPVC_SCH40, TradeSize.TWO_INCH,
     2.375, 11.0, 0.0, 90.0, "P90-200", 0.318, "NEC 352.24")


# ─────────────────────────────────────────────────────────────────────────────
# UPVC SCH 80 ELBOW 90° — NEC 352.24
# ─────────────────────────────────────────────────────────────────────────────
# Same OD and bend radius as UPVC Sch 40 per NEC Chapter 9, Table 4.
# Schedule 80 has thicker walls (smaller internal diameter) but the
# outside dimensions are identical. Catalog prefix 'S90-' distinguishes
# Sch 80 from Sch 40 ('P90-').

_reg(FittingType.ELBOW_90, ConduitType.UPVC_SCH80, TradeSize.HALF_INCH,
     0.840, 4.5, 0.0, 90.0, "S90-050", 0.045, "NEC 352.24")

_reg(FittingType.ELBOW_90, ConduitType.UPVC_SCH80, TradeSize.THREE_QUARTER,
     1.050, 5.25, 0.0, 90.0, "S90-075", 0.072, "NEC 352.24")

_reg(FittingType.ELBOW_90, ConduitType.UPVC_SCH80, TradeSize.ONE_INCH,
     1.315, 6.5, 0.0, 90.0, "S90-100", 0.110, "NEC 352.24")

_reg(FittingType.ELBOW_90, ConduitType.UPVC_SCH80, TradeSize.ONE_QUARTER,
     1.660, 8.0, 0.0, 90.0, "S90-125", 0.175, "NEC 352.24")

_reg(FittingType.ELBOW_90, ConduitType.UPVC_SCH80, TradeSize.ONE_HALF,
     1.900, 9.0, 0.0, 90.0, "S90-150", 0.230, "NEC 352.24")

_reg(FittingType.ELBOW_90, ConduitType.UPVC_SCH80, TradeSize.TWO_INCH,
     2.375, 11.0, 0.0, 90.0, "S90-200", 0.385, "NEC 352.24")


# ─────────────────────────────────────────────────────────────────────────────
# RGD ELBOW 90° — NEC 344.24
# ─────────────────────────────────────────────────────────────────────────────
# NEC 344.24 requires that bends in Rigid Metal Conduit be made with
# a radius that prevents conduit damage and maintains the internal
# diameter through the bend.
#
# OD and bend radius from NEC Chapter 9, Table 4 (RMC).

_reg(FittingType.ELBOW_90, ConduitType.RGD, TradeSize.HALF_INCH,
     0.840, 4.5, 0.0, 90.0, "R90-050", 0.136, "NEC 344.24")

_reg(FittingType.ELBOW_90, ConduitType.RGD, TradeSize.THREE_QUARTER,
     1.050, 5.25, 0.0, 90.0, "R90-075", 0.204, "NEC 344.24")

_reg(FittingType.ELBOW_90, ConduitType.RGD, TradeSize.ONE_INCH,
     1.315, 6.5, 0.0, 90.0, "R90-100", 0.340, "NEC 344.24")

_reg(FittingType.ELBOW_90, ConduitType.RGD, TradeSize.ONE_QUARTER,
     1.660, 8.0, 0.0, 90.0, "R90-125", 0.544, "NEC 344.24")

_reg(FittingType.ELBOW_90, ConduitType.RGD, TradeSize.ONE_HALF,
     1.900, 9.0, 0.0, 90.0, "R90-150", 0.725, "NEC 344.24")

_reg(FittingType.ELBOW_90, ConduitType.RGD, TradeSize.TWO_INCH,
     2.375, 11.0, 0.0, 90.0, "R90-200", 1.134, "NEC 344.24")


# ─────────────────────────────────────────────────────────────────────────────
# EMT COUPLINGS — NEC 358.42
# ─────────────────────────────────────────────────────────────────────────────
# NEC 358.42: Couplings and connectors for EMT shall be identified.
# Two types are cataloged:
#   EMT-C  — Compression coupling (threadless, rain-tight)
#   EMT-S  — Set-screw coupling (threadless, concrete-tight)
#
# EMT-C is registered first so get_fitting() returns the compression
# type by default. EMT-S is still available via all_fittings() by
# catalog number.

# EMT Compression couplings (EMT-C) — default for get_fitting()
_reg(FittingType.COUPLING, ConduitType.EMT, TradeSize.HALF_INCH,
     0.706, 0.0, 1.5, 0.0, "EC-050", 0.023, "NEC 358.42")

_reg(FittingType.COUPLING, ConduitType.EMT, TradeSize.THREE_QUARTER,
     0.922, 0.0, 1.75, 0.0, "EC-075", 0.036, "NEC 358.42")

# EMT Set-screw couplings (EMT-S) — stored in catalog, not in _INDEX
_reg(FittingType.COUPLING, ConduitType.EMT, TradeSize.HALF_INCH,
     0.706, 0.0, 1.25, 0.0, "ES-050", 0.018, "NEC 358.42")

_reg(FittingType.COUPLING, ConduitType.EMT, TradeSize.THREE_QUARTER,
     0.922, 0.0, 1.5, 0.0, "ES-075", 0.029, "NEC 358.42")


# ─────────────────────────────────────────────────────────────────────────────
# UPVC COUPLINGS — NEC 352.42
# ─────────────────────────────────────────────────────────────────────────────
# NEC 352.42: PVC couplings shall be of the solvent-cement or
# threaded type. Registered under UPVC_SCH40 as the primary schedule.
# The same coupling dimensions apply to Sch 80 conduit (identical OD).

_reg(FittingType.COUPLING, ConduitType.UPVC_SCH40, TradeSize.HALF_INCH,
     0.840, 0.0, 2.0, 0.0, "PC-050", 0.018, "NEC 352.42")

_reg(FittingType.COUPLING, ConduitType.UPVC_SCH40, TradeSize.THREE_QUARTER,
     1.050, 0.0, 2.25, 0.0, "PC-075", 0.027, "NEC 352.42")


# ─────────────────────────────────────────────────────────────────────────────
# RGD COUPLINGS — NEC 344.42
# ─────────────────────────────────────────────────────────────────────────────
# NEC 344.42: RMC couplings shall be threaded or threadless.
# Standard threaded couplings for rigid metal conduit.

_reg(FittingType.COUPLING, ConduitType.RGD, TradeSize.HALF_INCH,
     0.840, 0.0, 1.75, 0.0, "RC-050", 0.068, "NEC 344.42")

_reg(FittingType.COUPLING, ConduitType.RGD, TradeSize.THREE_QUARTER,
     1.050, 0.0, 2.0, 0.0, "RC-075", 0.113, "NEC 344.42")


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_fitting(
    conduit_type: ConduitType,
    trade_size: TradeSize,
    fitting_type: FittingType,
) -> Result[Fitting, CatalogError]:
    """Look up a fitting by conduit type, trade size, and fitting type.

    Returns Result.ok(Fitting) if a matching entry exists in the catalog,
    or Result.err(CatalogError) if no entry is found.

    For EMT couplings, the default entry is the compression type (EMT-C).
    Set-screw couplings (EMT-S) are available via ``all_fittings()``
    by catalog number ('ES-050', 'ES-075').

    SAFETY: This function NEVER raises. Callers must check ``is_ok()``
    before accessing ``.value``. Returning an error Result indicates
    the requested fitting is not listed — per NEC 110.3(B), unlisted
    equipment shall not be installed.

    Args:
        conduit_type: NEC conduit material designation (EMT, UPVC_SCH40,
                      UPVC_SCH80, RGD).
        trade_size:   Nominal trade size (HALF_INCH through TWO_INCH).
        fitting_type: Type of fitting (ELBOW_90, COUPLING, etc.).

    Returns:
        Result.ok(Fitting) on success, Result.err(CatalogError) on miss.

    Example::

        result = get_fitting(ConduitType.EMT, TradeSize.HALF_INCH,
                             FittingType.ELBOW_90)
        if result.is_ok():
            fitting = result.value
            print(fitting.catalog_number)  # 'E90-050'
            print(fitting.developed_length_in)  # 6.283
        else:
            print(result.error)  # CatalogError
    """
    key = (conduit_type, trade_size, fitting_type)
    catalog_number = _INDEX.get(key)
    if catalog_number is None:
        return Result.err(CatalogError(
            conduit_type=conduit_type.name,
            trade_size=trade_size.value,
            fitting_type=fitting_type.name,
        ))
    fitting = _CATALOG.get(catalog_number)
    if fitting is None:
        # Defensive: index points to missing catalog entry (should never happen)
        return Result.err(CatalogError(
            conduit_type=conduit_type.name,
            trade_size=trade_size.value,
            fitting_type=fitting_type.name,
        ))
    return Result.ok(fitting)


def catalog_size() -> int:
    """Return the total number of fittings in the catalog.

    This counts every unique catalog entry, including multiple coupling
    subtypes for the same conduit type (e.g. both EMT-C and EMT-S
    couplings).

    Returns:
        Number of registered Fitting objects.
    """
    return len(_CATALOG)


def all_fittings() -> Dict[str, Fitting]:
    """Return a shallow copy of the complete catalog.

    The returned dictionary is keyed by catalog_number (str) and
    contains every registered Fitting. Modifications to the returned
    dict do not affect the module-level catalog.

    SAFETY: The Fitting objects themselves are frozen dataclasses,
    so they cannot be mutated. However, the dict itself is a copy —
    callers may add or remove entries in their local copy without
    affecting the global catalog.

    Returns:
        Dict[str, Fitting] — catalog_number → Fitting copy.
    """
    return dict(_CATALOG)
