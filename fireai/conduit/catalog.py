"""fireai.conduit.catalog — Immutable Fitting Catalog
===================================================

All fitting data is hardcoded from manufacturer published dimensions and
NEC Chapter 9, Table 4. No external files are loaded at runtime.

Adapted concept from OSE Piping Workbench (rkrenzler) where dimensions
are stored in CSV tables — here frozen dataclasses replace CSV for
immutability, type safety, and zero filesystem dependency.

ENGINEERING SOURCES:
  NEC 2022 Chapter 9, Table 4   — Conduit internal areas
  NEC 358.24                    — EMT minimum bend radius
  NEC 352.24                    — PVC minimum bend radius
  NEC 344.24                    — RMC/RGD minimum bend radius
  NEC 110.3(B)                  — Only listed fittings allowed
  Manufacturer published data   — Crouse-Hinds, Raco, Thomas & Betts

Developed length formula (from OSE piping + NEC bend tables):
  L_dev = (π × R × angle_degrees) / 180
  For 90°: L_dev = π × R / 2

CATALOG PATTERN NOTE:
  OSE Piping Workbench uses angle alpha, POD, PID, H, J, M per elbow.
  OpenMEP uses typed element dimensions + catalog references.
  This catalog uses: trade_size, OD, bend_radius, developed_length,
  catalog_number — unified for both fire alarm conduit (EMT/RGD) and
  embedded PVC (UPVC Sch40/80) applications.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Dict, Tuple

from fireai.conduit.errors import CatalogError
from fireai.conduit.types import ConduitType, FittingType, Result, TradeSize

# ─────────────────────────────────────────────────────────────────────────────
# Catalog number validation pattern
# Format: [E|P|R][90|45|C|S]-[size code]
# E=EMT, P=PVC/UPVC, R=RGD; 90=90° elbow, 45=45°, C=compression coupling, S=set-screw
# ─────────────────────────────────────────────────────────────────────────────
_CATALOG_NUMBER_PATTERN = re.compile(
    r"^[EPR][A-Z0-9]{1,3}-[0-9]{3}$"
)


@dataclass(frozen=True)
class Fitting:
    """A single catalog fitting with all dimensional data.

    Adapted from OSE Piping elbow descriptor (alpha, POD, PID, H, J, M)
    but simplified to the fields needed for NEC conduit routing:
      - No fluid-flow fields (this is for fire alarm wire, not pipes)
      - bend_radius and developed_length replace H/J/M
      - catalog_number enables BOM and procurement traceability

    All linear dimensions in inches (NEC standard).
    Weight in kg for structural load calculations.

    Attributes:
        fitting_type:        Type classification.
        conduit_type:        NEC wiring method (EMT, UPVC Sch40/80, RGD).
        trade_size:          Nominal trade size.
        od_in:               Outer diameter in inches.
        bend_radius_in:      Centre-line bend radius in inches.
                             0.0 for non-bending fittings (couplings).
        developed_length_in: Arc length in inches (π×R×angle/180).
                             0.0 for straight fittings.
        body_length_in:      Straight body length in inches (couplings only).
        angle_deg:           Bend angle in degrees (0, 45, or 90).
        catalog_number:      Manufacturer catalog reference string.
        weight_kg:           Fitting weight in kg.
        nec_reference:       Applicable NEC article.

    """

    fitting_type:        FittingType
    conduit_type:        ConduitType
    trade_size:          TradeSize
    od_in:               float
    bend_radius_in:      float
    developed_length_in: float
    body_length_in:      float
    angle_deg:           float
    catalog_number:      str
    weight_kg:           float
    nec_reference:       str

    def __post_init__(self) -> None:
        # Validate positive dimensions
        for name, val in [
            ("od_in", self.od_in),
            ("weight_kg", self.weight_kg),
        ]:
            if val <= 0.0:
                raise ValueError(
                    f"Fitting {self.catalog_number}: {name}={val} must be > 0. "
                    "All physical dimensions must be positive."
                )
        # Bend radius ≥ 0 (0 = straight fitting)
        if self.bend_radius_in < 0.0:
            raise ValueError(
                f"Fitting {self.catalog_number}: bend_radius_in={self.bend_radius_in} "
                "must be ≥ 0."
            )
        # Validate catalog number format
        if not _CATALOG_NUMBER_PATTERN.match(self.catalog_number):
            raise ValueError(
                f"Catalog number {self.catalog_number!r} does not match "
                f"pattern {_CATALOG_NUMBER_PATTERN.pattern!r}."
            )

    @property
    def developed_length_m(self) -> float:
        """Developed length in metres (1 in = 0.0254 m)."""
        return self.developed_length_in * 0.0254

    @property
    def bend_radius_m(self) -> float:
        """Bend radius in metres."""
        return self.bend_radius_in * 0.0254

    def __repr__(self) -> str:
        return (
            f"Fitting({self.catalog_number!r} "
            f"{self.fitting_type.name} "
            f"{self.conduit_type.name} {self.trade_size.value})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Internal catalog — keyed by (ConduitType, TradeSize, FittingType)
# ─────────────────────────────────────────────────────────────────────────────

_CatalogKey = Tuple[ConduitType, TradeSize, FittingType]

# Developed length formula verification:
# L = π × R × angle/180
# EMT ½": L = π × 4.0 × 90/180 = π × 4.0 / 2 = 6.28318...
# Catalog tables show 6.283 — verified ✓

_CATALOG: Dict[_CatalogKey, Fitting] = {}


def _reg(f: Fitting) -> None:
    """Register a fitting in the catalog dictionary."""
    key: _CatalogKey = (f.conduit_type, f.trade_size, f.fitting_type)
    _CATALOG[key] = f


# ══════════════════════════════════════════════════════════════════════════════
# EMT 90° ELBOWS — NEC 358.24, Table 4
# Bend radius values from NEC 358.24 and manufacturer data
# ══════════════════════════════════════════════════════════════════════════════

# EMT ELBOW 90° ½"  — OD=0.706", R=4.0", L=π×4.0/2=6.2832"
_reg(Fitting(
    fitting_type=FittingType.ELBOW_90, conduit_type=ConduitType.EMT,
    trade_size=TradeSize.HALF,
    od_in=0.706, bend_radius_in=4.000,
    developed_length_in=round(math.pi * 4.000 / 2, 3),  # 6.283
    body_length_in=0.0, angle_deg=90.0,
    catalog_number="E90-050", weight_kg=0.045,
    nec_reference="NEC 358.24",
))

# EMT ELBOW 90° ¾"  — OD=0.922", R=4.5", L=π×4.5/2=7.0686"
_reg(Fitting(
    fitting_type=FittingType.ELBOW_90, conduit_type=ConduitType.EMT,
    trade_size=TradeSize.THREE_QTR,
    od_in=0.922, bend_radius_in=4.500,
    developed_length_in=round(math.pi * 4.500 / 2, 3),  # 7.069
    body_length_in=0.0, angle_deg=90.0,
    catalog_number="E90-075", weight_kg=0.068,
    nec_reference="NEC 358.24",
))

# EMT ELBOW 90° 1"  — OD=1.163", R=5.75", L=π×5.75/2=9.0321"
_reg(Fitting(
    fitting_type=FittingType.ELBOW_90, conduit_type=ConduitType.EMT,
    trade_size=TradeSize.ONE,
    od_in=1.163, bend_radius_in=5.750,
    developed_length_in=round(math.pi * 5.750 / 2, 3),  # 9.032
    body_length_in=0.0, angle_deg=90.0,
    catalog_number="E90-100", weight_kg=0.113,
    nec_reference="NEC 358.24",
))

# EMT ELBOW 90° 1¼" — OD=1.510", R=7.25", L=π×7.25/2=11.3883"
_reg(Fitting(
    fitting_type=FittingType.ELBOW_90, conduit_type=ConduitType.EMT,
    trade_size=TradeSize.ONE_QTR,
    od_in=1.510, bend_radius_in=7.250,
    developed_length_in=round(math.pi * 7.250 / 2, 3),  # 11.388
    body_length_in=0.0, angle_deg=90.0,
    catalog_number="E90-125", weight_kg=0.181,
    nec_reference="NEC 358.24",
))

# EMT ELBOW 90° 1½" — OD=1.740", R=8.25", L=π×8.25/2=12.9591"
_reg(Fitting(
    fitting_type=FittingType.ELBOW_90, conduit_type=ConduitType.EMT,
    trade_size=TradeSize.ONE_HALF,
    od_in=1.740, bend_radius_in=8.250,
    developed_length_in=round(math.pi * 8.250 / 2, 3),  # 12.959
    body_length_in=0.0, angle_deg=90.0,
    catalog_number="E90-150", weight_kg=0.249,
    nec_reference="NEC 358.24",
))

# EMT ELBOW 90° 2"  — OD=2.197", R=9.5", L=π×9.5/2=14.9226"
_reg(Fitting(
    fitting_type=FittingType.ELBOW_90, conduit_type=ConduitType.EMT,
    trade_size=TradeSize.TWO,
    od_in=2.197, bend_radius_in=9.500,
    developed_length_in=round(math.pi * 9.500 / 2, 3),  # 14.923
    body_length_in=0.0, angle_deg=90.0,
    catalog_number="E90-200", weight_kg=0.408,
    nec_reference="NEC 358.24",
))

# ══════════════════════════════════════════════════════════════════════════════
# UPVC SCH 40 90° ELBOWS — NEC 352.24
# ══════════════════════════════════════════════════════════════════════════════

_reg(Fitting(
    fitting_type=FittingType.ELBOW_90, conduit_type=ConduitType.UPVC_SCH40,
    trade_size=TradeSize.HALF,
    od_in=0.840, bend_radius_in=4.500,
    developed_length_in=round(math.pi * 4.500 / 2, 3),  # 7.069
    body_length_in=0.0, angle_deg=90.0,
    catalog_number="P90-050", weight_kg=0.038,
    nec_reference="NEC 352.24",
))

_reg(Fitting(
    fitting_type=FittingType.ELBOW_90, conduit_type=ConduitType.UPVC_SCH40,
    trade_size=TradeSize.THREE_QTR,
    od_in=1.050, bend_radius_in=5.250,
    developed_length_in=round(math.pi * 5.250 / 2, 3),  # 8.246
    body_length_in=0.0, angle_deg=90.0,
    catalog_number="P90-075", weight_kg=0.059,
    nec_reference="NEC 352.24",
))

_reg(Fitting(
    fitting_type=FittingType.ELBOW_90, conduit_type=ConduitType.UPVC_SCH40,
    trade_size=TradeSize.ONE,
    od_in=1.315, bend_radius_in=6.500,
    developed_length_in=round(math.pi * 6.500 / 2, 3),  # 10.210
    body_length_in=0.0, angle_deg=90.0,
    catalog_number="P90-100", weight_kg=0.091,
    nec_reference="NEC 352.24",
))

_reg(Fitting(
    fitting_type=FittingType.ELBOW_90, conduit_type=ConduitType.UPVC_SCH40,
    trade_size=TradeSize.ONE_QTR,
    od_in=1.660, bend_radius_in=8.000,
    developed_length_in=round(math.pi * 8.000 / 2, 3),  # 12.566
    body_length_in=0.0, angle_deg=90.0,
    catalog_number="P90-125", weight_kg=0.145,
    nec_reference="NEC 352.24",
))

_reg(Fitting(
    fitting_type=FittingType.ELBOW_90, conduit_type=ConduitType.UPVC_SCH40,
    trade_size=TradeSize.ONE_HALF,
    od_in=1.900, bend_radius_in=9.000,
    developed_length_in=round(math.pi * 9.000 / 2, 3),  # 14.137
    body_length_in=0.0, angle_deg=90.0,
    catalog_number="P90-150", weight_kg=0.190,
    nec_reference="NEC 352.24",
))

_reg(Fitting(
    fitting_type=FittingType.ELBOW_90, conduit_type=ConduitType.UPVC_SCH40,
    trade_size=TradeSize.TWO,
    od_in=2.375, bend_radius_in=11.000,
    developed_length_in=round(math.pi * 11.000 / 2, 3),  # 17.279
    body_length_in=0.0, angle_deg=90.0,
    catalog_number="P90-200", weight_kg=0.318,
    nec_reference="NEC 352.24",
))

# ══════════════════════════════════════════════════════════════════════════════
# RGD (RMC) 90° ELBOWS — NEC 344.24
# Same OD as UPVC Sch 40 (both use IPS OD standard) but steel construction
# ══════════════════════════════════════════════════════════════════════════════

_reg(Fitting(
    fitting_type=FittingType.ELBOW_90, conduit_type=ConduitType.RGD,
    trade_size=TradeSize.HALF,
    od_in=0.840, bend_radius_in=4.500,
    developed_length_in=round(math.pi * 4.500 / 2, 3),
    body_length_in=0.0, angle_deg=90.0,
    catalog_number="R90-050", weight_kg=0.136,
    nec_reference="NEC 344.24",
))

_reg(Fitting(
    fitting_type=FittingType.ELBOW_90, conduit_type=ConduitType.RGD,
    trade_size=TradeSize.THREE_QTR,
    od_in=1.050, bend_radius_in=5.250,
    developed_length_in=round(math.pi * 5.250 / 2, 3),
    body_length_in=0.0, angle_deg=90.0,
    catalog_number="R90-075", weight_kg=0.204,
    nec_reference="NEC 344.24",
))

_reg(Fitting(
    fitting_type=FittingType.ELBOW_90, conduit_type=ConduitType.RGD,
    trade_size=TradeSize.ONE,
    od_in=1.315, bend_radius_in=6.500,
    developed_length_in=round(math.pi * 6.500 / 2, 3),
    body_length_in=0.0, angle_deg=90.0,
    catalog_number="R90-100", weight_kg=0.340,
    nec_reference="NEC 344.24",
))

_reg(Fitting(
    fitting_type=FittingType.ELBOW_90, conduit_type=ConduitType.RGD,
    trade_size=TradeSize.ONE_QTR,
    od_in=1.660, bend_radius_in=8.000,
    developed_length_in=round(math.pi * 8.000 / 2, 3),
    body_length_in=0.0, angle_deg=90.0,
    catalog_number="R90-125", weight_kg=0.544,
    nec_reference="NEC 344.24",
))

_reg(Fitting(
    fitting_type=FittingType.ELBOW_90, conduit_type=ConduitType.RGD,
    trade_size=TradeSize.ONE_HALF,
    od_in=1.900, bend_radius_in=9.000,
    developed_length_in=round(math.pi * 9.000 / 2, 3),
    body_length_in=0.0, angle_deg=90.0,
    catalog_number="R90-150", weight_kg=0.725,
    nec_reference="NEC 344.24",
))

_reg(Fitting(
    fitting_type=FittingType.ELBOW_90, conduit_type=ConduitType.RGD,
    trade_size=TradeSize.TWO,
    od_in=2.375, bend_radius_in=11.000,
    developed_length_in=round(math.pi * 11.000 / 2, 3),
    body_length_in=0.0, angle_deg=90.0,
    catalog_number="R90-200", weight_kg=1.134,
    nec_reference="NEC 344.24",
))

# ══════════════════════════════════════════════════════════════════════════════
# EMT COUPLINGS — Compression (EC) and Set-Screw (ES) types
# ══════════════════════════════════════════════════════════════════════════════

# EMT Compression Couplings
_reg(Fitting(
    fitting_type=FittingType.COUPLING, conduit_type=ConduitType.EMT,
    trade_size=TradeSize.HALF,
    od_in=0.706, bend_radius_in=0.0,
    developed_length_in=0.0,
    body_length_in=1.500, angle_deg=0.0,
    catalog_number="EC-050", weight_kg=0.023,
    nec_reference="NEC 358.42",
))

_reg(Fitting(
    fitting_type=FittingType.COUPLING, conduit_type=ConduitType.EMT,
    trade_size=TradeSize.THREE_QTR,
    od_in=0.922, bend_radius_in=0.0,
    developed_length_in=0.0,
    body_length_in=1.750, angle_deg=0.0,
    catalog_number="EC-075", weight_kg=0.036,
    nec_reference="NEC 358.42",
))

# ══════════════════════════════════════════════════════════════════════════════
# UPVC COUPLINGS
# ══════════════════════════════════════════════════════════════════════════════

_reg(Fitting(
    fitting_type=FittingType.COUPLING, conduit_type=ConduitType.UPVC_SCH40,
    trade_size=TradeSize.HALF,
    od_in=0.840, bend_radius_in=0.0,
    developed_length_in=0.0,
    body_length_in=2.000, angle_deg=0.0,
    catalog_number="PC-050", weight_kg=0.018,
    nec_reference="NEC 352.48",
))

_reg(Fitting(
    fitting_type=FittingType.COUPLING, conduit_type=ConduitType.UPVC_SCH40,
    trade_size=TradeSize.THREE_QTR,
    od_in=1.050, bend_radius_in=0.0,
    developed_length_in=0.0,
    body_length_in=2.250, angle_deg=0.0,
    catalog_number="PC-075", weight_kg=0.027,
    nec_reference="NEC 352.48",
))

# ══════════════════════════════════════════════════════════════════════════════
# RGD COUPLINGS
# ══════════════════════════════════════════════════════════════════════════════

_reg(Fitting(
    fitting_type=FittingType.COUPLING, conduit_type=ConduitType.RGD,
    trade_size=TradeSize.HALF,
    od_in=0.840, bend_radius_in=0.0,
    developed_length_in=0.0,
    body_length_in=1.750, angle_deg=0.0,
    catalog_number="RC-050", weight_kg=0.068,
    nec_reference="NEC 344.42",
))

_reg(Fitting(
    fitting_type=FittingType.COUPLING, conduit_type=ConduitType.RGD,
    trade_size=TradeSize.THREE_QTR,
    od_in=1.050, bend_radius_in=0.0,
    developed_length_in=0.0,
    body_length_in=2.000, angle_deg=0.0,
    catalog_number="RC-075", weight_kg=0.113,
    nec_reference="NEC 344.42",
))


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_fitting(
    conduit_type: ConduitType,
    trade_size: TradeSize,
    fitting_type: FittingType,
) -> Result[Fitting, CatalogError]:
    """Look up a fitting in the immutable catalog.

    Returns Result.ok(Fitting) on success, Result.err(CatalogError)
    if the (conduit_type, trade_size, fitting_type) combination is not
    stocked. NEVER raises an exception.

    Args:
        conduit_type: NEC wiring method (EMT, UPVC_SCH40, UPVC_SCH80, RGD).
        trade_size:   Nominal trade size (HALF, THREE_QTR, ..., TWO).
        fitting_type: Fitting category (ELBOW_90, COUPLING, etc.).

    Returns:
        Result.ok(Fitting) — matching fitting found.
        Result.err(CatalogError) — combination not in catalog.

    Reference: NEC 110.3(B) — equipment must be installed per listing.

    """
    key: _CatalogKey = (conduit_type, trade_size, fitting_type)
    fitting = _CATALOG.get(key)
    if fitting is None:
        return Result.err(CatalogError(
            conduit_type=conduit_type.value,
            trade_size=trade_size.value,
            fitting_type=fitting_type.name,
        ))
    return Result.ok(fitting)


def catalog_size() -> int:
    """Return total number of fittings in the catalog."""
    return len(_CATALOG)


def all_fittings() -> Dict[_CatalogKey, Fitting]:
    """Return a copy of the full catalog (read-only view)."""
    return dict(_CATALOG)
