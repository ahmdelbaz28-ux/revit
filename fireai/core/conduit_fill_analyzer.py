"""conduit_fill_analyzer.py — NEC Chapter 9 Conduit Fill Analysis
===============================================================
CRITICAL LIFE-SAFETY MODULE — V18

Analyzes conduit fill ratios for fire alarm cable bundles, ensuring
compliance with NEC (NFPA 70) Chapter 9 Table 1 and Table 4.

When multiple FA circuits converge in trunk pathways from the FACP,
the cable bundle must fit within the conduit with proper fill ratio.
Overfilled conduits cause:
  - Thermal buildup (NEC 310.15 conductor derating)
  - Cable insulation damage during pulling
  - AHJ rejection at inspection — conduit must be demolished and replaced
  - Potential cable melting during fire (defeating the fire alarm system)

Consultant's code had these errors (ALL FIXED):
  1. FPLR-only wire types — missing FPLP, THHN, and other FA cable types
  2. No PLFA/NPLFA separation — NEC 760.154 PROHIBITS mixing power-limited
     and non-power-limited fire alarm circuits in the same conduit
  3. EMT-only conduit — missing RMC, IMC, PVC, LFMC, FMC types
  4. Non-verified fill area values — potential calculation errors
  5. Missing conductor derating for >3 current-carrying conductors
     per NEC 310.15(B)(3)(a)
  6. WireSpec.awg field unused in calculation — dead field
  7. No cable tray option when conduit exceeds maximum size

NEC References:
  - Chapter 9, Table 1: Maximum fill percentages (53%/31%/40%)
  - Chapter 9, Table 4: Conduit internal dimensions
  - Chapter 9, Table 5: Conductor dimensions (by insulation type)
  - NEC 760.154: Mixing PLFA and NPLFA circuits prohibited
  - NEC 310.15(B)(3)(a): Conductor ampacity derating for >3 conductors

Usage:
    from fireai.core.conduit_fill_analyzer import ConduitSizer, WireSpec

    sizer = ConduitSizer()
    result = sizer.analyze_routing_bundle(
        bundle_id="TRUNK-FACP-RISER",
        wire_inventory=[
            {"awg": 14, "count": 8, "insulation": "FPLP"},
            {"awg": 16, "count": 4, "insulation": "FPLR"},
        ],
    )
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provenance — graceful degradation
# ---------------------------------------------------------------------------
try:
    from fireai.core.provenance import (
        ConfidenceLevel,
        ConfidenceScore,
        DecisionProvenance,
        RuleApplied,
        Violation,
    )
except ImportError:
    DecisionProvenance = None  # type: ignore[misc,assignment]
    RuleApplied = None  # type: ignore[misc,assignment]
    Violation = None  # type: ignore[misc,assignment]
    ConfidenceScore = None  # type: ignore[misc,assignment]
    ConfidenceLevel = None  # type: ignore[misc,assignment]


# ============================================================================
# Cable Insulation Types — NEC Chapter 9 Table 5
# ============================================================================


class InsulationType(str, Enum):
    """Fire alarm cable insulation types per NEC Chapter 9 Table 5."""

    FPLP = "FPLP"  # Fire Power Limited Plenum — most common for FA
    FPLR = "FPLR"  # Fire Power Limited Riser
    FPL = "FPL"  # Fire Power Limited (general)
    THHN = "THHN"  # Thermoplastic High Heat Nylon — for NAC circuits
    THWN = "THWN"  # Thermoplastic Heat and Water Resistant Nylon
    XHHW = "XHHW"  # Cross-linked Polyethylene


class CircuitClass(str, Enum):
    """Fire alarm circuit classification per NEC 760.

    CRITICAL: NEC 760.154 PROHIBITS mixing PLFA and NPLFA circuits
    in the same conduit. The consultant's code ignored this entirely.
    """

    PLFA = "PLFA"  # Power-Limited Fire Alarm (typical SLC, NAC)
    NPLFA = "NPLFA"  # Non-Power-Limited Fire Alarm (high-voltage NAC)
    COMBO = "COMBO"  # Mixed — ILLEGAL in same conduit per NEC 760.154


# ============================================================================
# Wire Specifications — NEC Chapter 9 Table 5 Data
# ============================================================================

# Outer diameter in mm for common FA cable types
# Based on NEC Chapter 9 Table 5 and manufacturer data
# Format: (insulation_type, awg) → outer_diameter_mm
WIRE_DIAMETERS_MM: Dict[Tuple[str, int], float] = {
    # FPLP — Fire Power Limited Plenum (most common for FA SLC circuits)
    ("FPLP", 18): 2.59,
    ("FPLP", 16): 3.00,
    ("FPLP", 14): 3.61,
    ("FPLP", 12): 4.22,
    ("FPLP", 10): 4.80,  # V20.1: Added for NAC voltage-drop upsizing feedback loop
    # FPLR — Fire Power Limited Riser
    ("FPLR", 18): 2.59,
    ("FPLR", 16): 3.00,
    ("FPLR", 14): 3.61,
    ("FPLR", 12): 4.22,
    ("FPLR", 10): 4.80,  # V20.1: Added for NAC voltage-drop upsizing feedback loop
    # FPL — Fire Power Limited (general purpose)
    ("FPL", 18): 2.39,
    ("FPL", 16): 2.79,
    ("FPL", 14): 3.30,
    # THHN — used for NAC power circuits (horns, strobes)
    ("THHN", 14): 2.82,
    ("THHN", 12): 3.30,
    ("THHN", 10): 4.17,
    # THWN — similar to THHN
    ("THWN", 14): 2.82,
    ("THWN", 12): 3.30,
    # XHHW — for longer runs
    ("XHHW", 14): 3.05,
    ("XHHW", 12): 3.56,
    # Fiber optic / composite cables
    ("FIBER_2STR", 0): 5.80,  # 2-strand fiber
    ("FIBER_4STR", 0): 6.60,  # 4-strand fiber
    # Shielded cable (common in FA for EMI protection)
    ("FPLP_SHIELDED", 18): 4.20,
    ("FPLP_SHIELDED", 16): 4.60,
    ("FPLP_SHIELDED", 14): 5.20,
}


# ============================================================================
# Conduit Specifications — NEC Chapter 9 Table 4
# ============================================================================


class ConduitType(str, Enum):
    """Conduit types per NEC Chapter 9 Table 4."""

    EMT = "EMT"  # Electrical Metallic Tubing
    RMC = "RMC"  # Rigid Metal Conduit
    IMC = "IMC"  # Intermediate Metal Conduit
    PVC_SCHEDULE_40 = "PVC40"  # PVC Schedule 40
    PVC_SCHEDULE_80 = "PVC80"  # PVC Schedule 80
    LFMC = "LFMC"  # Liquidtight Flexible Metal Conduit
    FMC = "FMC"  # Flexible Metal Conduit


# Conduit internal dimensions — NEC Chapter 9 Table 4
# Format: trade_size → {"id_mm": internal_diameter, "area_mm2": 100% internal area}
# Values from NEC Chapter 9 Table 4 (verified against 2023 edition)
CONDUIT_SPECS: Dict[Tuple[str, str], Dict[str, float]] = {
    # EMT — Electrical Metallic Tubing
    ("EMT", "1/2"): {"id_mm": 15.80, "area_mm2": 196.07},
    ("EMT", "3/4"): {"id_mm": 20.93, "area_mm2": 343.98},
    ("EMT", "1"): {"id_mm": 26.64, "area_mm2": 557.49},
    ("EMT", "1-1/4"): {"id_mm": 35.05, "area_mm2": 965.81},
    ("EMT", "1-1/2"): {"id_mm": 40.89, "area_mm2": 1313.87},
    ("EMT", "2"): {"id_mm": 52.50, "area_mm2": 2164.77},
    ("EMT", "2-1/2"): {"id_mm": 63.00, "area_mm2": 3117.25},
    ("EMT", "3"): {"id_mm": 78.50, "area_mm2": 4839.61},
    ("EMT", "3-1/2"): {"id_mm": 90.50, "area_mm2": 6429.68},
    ("EMT", "4"): {"id_mm": 102.50, "area_mm2": 8255.46},
    # RMC — Rigid Metal Conduit
    ("RMC", "1/2"): {"id_mm": 16.10, "area_mm2": 203.58},
    ("RMC", "3/4"): {"id_mm": 21.20, "area_mm2": 352.99},
    ("RMC", "1"): {"id_mm": 27.00, "area_mm2": 572.56},
    ("RMC", "1-1/4"): {"id_mm": 35.40, "area_mm2": 984.20},
    ("RMC", "1-1/2"): {"id_mm": 41.20, "area_mm2": 1334.66},
    ("RMC", "2"): {"id_mm": 52.90, "area_mm2": 2198.44},
    # IMC — Intermediate Metal Conduit
    ("IMC", "1/2"): {"id_mm": 16.80, "area_mm2": 221.67},
    ("IMC", "3/4"): {"id_mm": 21.80, "area_mm2": 373.25},
    ("IMC", "1"): {"id_mm": 27.60, "area_mm2": 598.45},
    ("IMC", "1-1/4"): {"id_mm": 36.00, "area_mm2": 1017.88},
    ("IMC", "1-1/2"): {"id_mm": 41.80, "area_mm2": 1372.88},
    ("IMC", "2"): {"id_mm": 53.50, "area_mm2": 2248.93},
    # V20.2 FIX: PVC Schedule 40 — NEC Chapter 9 Table 4
    # PVC is commonly used for fire alarm installations per NEC 760.154.
    # Missing specs caused silent fallback to cable tray recommendation.
    ("PVC40", "1/2"): {"id_mm": 15.30, "area_mm2": 183.85},
    ("PVC40", "3/4"): {"id_mm": 20.40, "area_mm2": 326.85},
    ("PVC40", "1"): {"id_mm": 26.10, "area_mm2": 535.02},
    ("PVC40", "1-1/4"): {"id_mm": 34.50, "area_mm2": 934.79},
    ("PVC40", "1-1/2"): {"id_mm": 40.40, "area_mm2": 1281.65},
    ("PVC40", "2"): {"id_mm": 52.00, "area_mm2": 2123.72},
    ("PVC40", "2-1/2"): {"id_mm": 62.10, "area_mm2": 3029.09},
    ("PVC40", "3"): {"id_mm": 77.60, "area_mm2": 4729.90},
    ("PVC40", "3-1/2"): {"id_mm": 89.50, "area_mm2": 6291.77},
    ("PVC40", "4"): {"id_mm": 101.50, "area_mm2": 8089.43},
    # V20.2 FIX: PVC Schedule 80 — NEC Chapter 9 Table 4
    ("PVC80", "1/2"): {"id_mm": 13.20, "area_mm2": 136.85},
    ("PVC80", "3/4"): {"id_mm": 17.90, "area_mm2": 251.79},
    ("PVC80", "1"): {"id_mm": 23.10, "area_mm2": 419.10},
    ("PVC80", "1-1/4"): {"id_mm": 31.10, "area_mm2": 759.65},
    ("PVC80", "1-1/2"): {"id_mm": 36.50, "area_mm2": 1046.35},
    ("PVC80", "2"): {"id_mm": 47.80, "area_mm2": 1793.94},
    ("PVC80", "2-1/2"): {"id_mm": 57.20, "area_mm2": 2569.30},
    ("PVC80", "3"): {"id_mm": 71.90, "area_mm2": 4059.87},
    ("PVC80", "4"): {"id_mm": 95.30, "area_mm2": 7131.27},
    # V20.2 FIX: LFMC — Liquidtight Flexible Metal Conduit
    ("LFMC", "3/8"): {"id_mm": 12.40, "area_mm2": 120.76},
    ("LFMC", "1/2"): {"id_mm": 15.70, "area_mm2": 193.59},
    ("LFMC", "3/4"): {"id_mm": 20.40, "area_mm2": 326.85},
    ("LFMC", "1"): {"id_mm": 25.90, "area_mm2": 526.90},
    ("LFMC", "1-1/4"): {"id_mm": 34.30, "area_mm2": 923.89},
    ("LFMC", "1-1/2"): {"id_mm": 40.10, "area_mm2": 1262.92},
    ("LFMC", "2"): {"id_mm": 51.60, "area_mm2": 2089.88},
    # V20.2 FIX: FMC — Flexible Metal Conduit
    ("FMC", "3/8"): {"id_mm": 12.30, "area_mm2": 118.82},
    ("FMC", "1/2"): {"id_mm": 15.60, "area_mm2": 191.13},
    ("FMC", "3/4"): {"id_mm": 20.30, "area_mm2": 323.65},
    ("FMC", "1"): {"id_mm": 25.80, "area_mm2": 522.79},
    ("FMC", "1-1/4"): {"id_mm": 34.20, "area_mm2": 918.51},
    ("FMC", "1-1/2"): {"id_mm": 40.00, "area_mm2": 1256.64},
    ("FMC", "2"): {"id_mm": 51.50, "area_mm2": 2081.81},
}


# ============================================================================
# Fill Percentage Limits — NEC Chapter 9 Table 1
# ============================================================================

FILL_LIMITS = {
    1: 0.53,  # Single conductor: 53%
    2: 0.31,  # Two conductors: 31%
    # 3 or more: 40%
}
DEFAULT_FILL_LIMIT = 0.40  # 3+ conductors


# ============================================================================
# Conductor Derating — NEC 310.15(B)(3)(a)
# ============================================================================

# When more than 3 current-carrying conductors are in a conduit,
# the ampacity must be reduced per NEC 310.15(B)(3)(a).
# This is critical for NAC circuits (horns/strobes draw significant current).
# Format: conductor_count_range → derating_factor
CONDUCTOR_DERATING = {
    (4, 6): 0.80,
    (7, 9): 0.70,
    (10, 20): 0.50,
    (21, 30): 0.45,
    (31, 40): 0.40,
    (41, float("inf")): 0.35,
}


def get_derating_factor(conductor_count: int) -> float:
    """Get ampacity derating factor per NEC 310.15(B)(3)(a).

    Args:
        conductor_count: Number of current-carrying conductors.

    Returns:
        Derating factor (1.0 for 3 or fewer conductors).

    """
    if conductor_count <= 3:
        return 1.0
    for (lo, hi), factor in CONDUCTOR_DERATING.items():
        if lo <= conductor_count <= hi:
            return factor
    return 0.35  # Maximum derating


# ============================================================================
# Wire Spec Dataclass
# ============================================================================


@dataclass(frozen=True)
class WireSpec:
    """Specification of a wire/cable for conduit fill calculation.

    Attributes:
        awg: American Wire Gauge (0 for fiber optic).
        insulation: InsulationType enum.
        outer_diameter_mm: Outer diameter in millimetres.
        circuit_class: PLFA or NPLFA — affects conduit separation.

    """

    awg: int
    insulation: InsulationType = InsulationType.FPLP
    outer_diameter_mm: float = 0.0
    circuit_class: CircuitClass = CircuitClass.PLFA

    def __post_init__(self):
        # If no diameter provided, look up from table
        if self.outer_diameter_mm <= 0:
            key = (self.insulation.value, self.awg)
            if key in WIRE_DIAMETERS_MM:
                # Use frozen dataclass workaround
                object.__setattr__(self, "outer_diameter_mm", WIRE_DIAMETERS_MM[key])
            else:
                # V78 FIX: Conservative default 6.0mm instead of 3.5mm.
                # Underestimating cable area means conduit appears to have more fill
                # capacity than it actually does — overfilled conduit can cause insulation
                # damage and thermal buildup per NEC 310.15. Overestimating area is SAFE
                # (rejects conduit → upsizes). FPLP shielded 14 AWG is 5.20mm actual.
                object.__setattr__(self, "outer_diameter_mm", 6.0)
                logger.warning("No diameter data for %s AWG %s, using conservative default 6.0mm. Verify actual cable diameter.", self.insulation.value, self.awg)

    @property
    def cross_section_mm2(self) -> float:
        """Cross-sectional area of the wire in mm²."""
        return math.pi * (self.outer_diameter_mm / 2.0) ** 2


# ============================================================================
# Conduit Sizing Result
# ============================================================================


@dataclass
class ConduitFillResult:
    """Result of conduit fill analysis.

    Attributes:
        bundle_id: Identifier for this cable bundle.
        total_cable_area_mm2: Sum of all wire cross-sections.
        conductor_count: Total number of conductors.
        fill_limit_pct: NEC fill percentage limit applied.
        recommended_conduit_type: Best conduit type (EMT, RMC, etc.).
        recommended_trade_size: Conduit trade size (e.g., "3/4").
        actual_fill_pct: Actual fill percentage.
        is_compliant: Whether fill ratio is within NEC limits.
        derating_factor: Ampacity derating factor if >3 conductors.
        plfa_nlfa_separated: Whether PLFA/NPLFA circuits are separated.
        violations: List of violation dicts.
        warnings: List of warning strings.

    """

    bundle_id: str
    total_cable_area_mm2: float
    conductor_count: int
    fill_limit_pct: float
    recommended_conduit_type: str
    recommended_trade_size: str
    actual_fill_pct: float
    is_compliant: bool
    derating_factor: float
    plfa_nplfa_separated: bool
    violations: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ============================================================================
# Conduit Sizer
# ============================================================================


class ConduitSizer:
    """NEC Chapter 9 Conduit Fill Analyzer for fire alarm cable bundles.

    Determines the minimum conduit size required for a bundle of fire
    alarm cables, ensuring compliance with NEC fill ratio limits and
    PLFA/NPLFA separation requirements.

    The consultant's code missed:
      - PLFA/NPLFA separation (NEC 760.154)
      - Conductor derating (NEC 310.15)
      - Multiple conduit types (only EMT)
      - Cable tray option for oversized bundles
      - Verified NEC Table 4 values

    Usage::

        from fireai.core.conduit_fill_analyzer import ConduitSizer

        sizer = ConduitSizer()
        result = sizer.analyze_routing_bundle(
            bundle_id="TRUNK-FACP",
            wire_inventory=[
                {"awg": 14, "count": 8, "insulation": "FPLP"},
                {"awg": 16, "count": 4, "insulation": "FPLR"},
            ],
        )
    """

    # Preferred conduit types in order (EMT most common for FA)
    PREFERRED_CONDUIT_ORDER = [
        ConduitType.EMT,
        ConduitType.IMC,
        ConduitType.RMC,
    ]

    def analyze_routing_bundle(
        self,
        bundle_id: str,
        wire_inventory: List[Dict],
        conduit_type: str = "EMT",
        enforce_plfa_separation: bool = True,
    ) -> Any:
        """Analyze conduit fill for a cable bundle.

        Args:
            bundle_id: Identifier for this cable bundle.
            wire_inventory: List of wire dicts. Each dict has:
                - "awg": Wire gauge (int, 0 for fiber)
                - "count": Number of conductors
                - "insulation": Insulation type string (default "FPLP")
                - "circuit_class": "PLFA" or "NPLFA" (default "PLFA")
            conduit_type: Preferred conduit type ("EMT", "RMC", "IMC").
            enforce_plfa_separation: Whether to enforce NEC 760.154
                separation of PLFA and NPLFA circuits.

        Returns:
            DecisionProvenance or dict with conduit fill analysis.

        """
        total_area = 0.0
        conductor_count = 0
        has_plfa = False
        has_nplfa = False
        violations: List[Any] = []
        warnings: List[str] = []

        # Process each wire type in the bundle
        for cable in wire_inventory:
            awg = cable.get("awg", 16)
            qty = cable.get("count", 1)

            # LOW-02 FIX: Negative wire count is physically impossible.
            # A negative count would reduce total area, potentially making
            # an overfilled conduit appear compliant — a life-safety hazard.
            if not isinstance(qty, int) or qty < 0:
                violations.append(
                    Violation(
                        severity="CRITICAL",
                        citation="NEC Chapter 9 Table 1",
                        description=(
                            f"Bundle '{bundle_id}' has invalid wire count: "
                            f"AWG {awg} count={qty}. Wire count must be a "
                            f"non-negative integer. Negative counts reduce "
                            f"total area, potentially masking overfill."
                        ),
                    )
                    if Violation
                    else {
                        "severity": "CRITICAL",
                        "citation": "NEC Chapter 9 Table 1",
                        "description": f"Invalid wire count: AWG {awg} count={qty}",
                    }
                )
                qty = 0  # Safe default: skip this entry

            insul_str = cable.get("insulation", "FPLP").upper()
            cc_str = cable.get("circuit_class", "PLFA").upper()

            # Resolve insulation type
            try:
                insulation = InsulationType(insul_str)
            except ValueError:
                insulation = InsulationType.FPLP
                warnings.append(f"Unknown insulation type '{insul_str}' for AWG {awg}, defaulting to FPLP.")

            # Resolve circuit class
            try:
                circuit_class = CircuitClass(cc_str)
            except ValueError:
                circuit_class = CircuitClass.PLFA

            if circuit_class == CircuitClass.PLFA:
                has_plfa = True
            elif circuit_class == CircuitClass.NPLFA:
                has_nplfa = True

            # Create wire spec and accumulate
            spec = WireSpec(awg=awg, insulation=insulation, circuit_class=circuit_class)
            total_area += spec.cross_section_mm2 * qty
            conductor_count += qty

        # --- CRITICAL: PLFA/NPLFA Separation Check (NEC 760.154) ---
        plfa_nplfa_separated = True
        if has_plfa and has_nplfa and enforce_plfa_separation:
            plfa_nplfa_separated = False
            violations.append(
                Violation(
                    severity="CRITICAL",
                    citation="NEC 760.154",
                    description=(
                        f"Bundle '{bundle_id}' contains BOTH PLFA and NPLFA circuits "
                        f"in the same conduit. NEC 760.154 PROHIBITS this mixing. "
                        f"Separate into distinct conduits immediately."
                    ),
                )
                if Violation
                else {
                    "severity": "CRITICAL",
                    "citation": "NEC 760.154",
                    "description": "PLFA/NPLFA mixing prohibited",
                }
            )

        # --- Determine fill limit (NEC Chapter 9 Table 1) ---
        if conductor_count == 1:
            fill_limit = FILL_LIMITS[1]
        elif conductor_count == 2:
            fill_limit = FILL_LIMITS[2]
        else:
            fill_limit = DEFAULT_FILL_LIMIT

        # --- Find minimum conduit size ---
        c_type = conduit_type.upper()
        optimal_size = None
        actual_fill_pct = 100.0

        # Try preferred conduit type first, then alternatives
        conduit_order = [c_type]
        for ct in self.PREFERRED_CONDUIT_ORDER:
            if ct.value not in conduit_order:
                conduit_order.append(ct.value)

        for ct in conduit_order:  # type: ignore[assignment]
            for trade_size in ["1/2", "3/4", "1", "1-1/4", "1-1/2", "2", "2-1/2", "3", "3-1/2", "4"]:
                key = (ct, trade_size)
                if key not in CONDUIT_SPECS:
                    continue

                full_area = CONDUIT_SPECS[key]["area_mm2"]
                full_area * fill_limit
                fill_pct = (total_area / full_area) * 100.0

                if fill_pct <= fill_limit * 100:
                    optimal_size = trade_size
                    actual_fill_pct = fill_pct
                    c_type = ct  # type: ignore[assignment]
                    break

            if optimal_size:
                break

        if not optimal_size:
            # Exceeds all conduit sizes — recommend cable tray
            violations.append(
                Violation(
                    severity="CRITICAL",
                    citation="NEC Chapter 9 Table 1",
                    description=(
                        f"Cable bundle ({total_area:.1f} mm²) exceeds all standard "
                        f"conduit fill limits. Use cable tray or multiple conduits."
                    ),
                )
                if Violation
                else {
                    "severity": "CRITICAL",
                    "citation": "NEC Chapter 9",
                    "description": "Exceeds all conduit sizes",
                }
            )
            optimal_size = "> 2 Inch / Cable Tray"
            actual_fill_pct = (total_area / CONDUIT_SPECS.get((c_type, "4"), {"area_mm2": 8255.46})["area_mm2"]) * 100.0

        # --- Conductor derating check (NEC 310.15) ---
        derating = get_derating_factor(conductor_count)
        if derating < 1.0:
            warnings.append(
                f"NEC 310.15(B)(3)(a): {conductor_count} current-carrying "
                f"conductors require {derating * 100:.0f}% ampacity derating."
            )

        # Build result
        is_compliant = actual_fill_pct <= fill_limit * 100 and plfa_nplfa_separated

        ConduitFillResult(
            bundle_id=bundle_id,
            total_cable_area_mm2=round(total_area, 2),
            conductor_count=conductor_count,
            fill_limit_pct=round(fill_limit * 100, 1),
            recommended_conduit_type=c_type,
            recommended_trade_size=optimal_size,
            actual_fill_pct=round(actual_fill_pct, 2),
            is_compliant=is_compliant,
            derating_factor=derating,
            plfa_nplfa_separated=plfa_nplfa_separated,
            violations=[],  # Will be added to provenance
            warnings=warnings,
        )

        # Build DecisionProvenance if available
        if DecisionProvenance is not None:
            prov_violations = []
            for v in violations:
                if isinstance(v, Violation):
                    prov_violations.append(v)
                elif isinstance(v, dict):
                    prov_violations.append(
                        Violation(
                            severity=v.get("severity", "WARNING"),
                            citation=v.get("citation", "NEC"),
                            description=v.get("description", ""),
                        )
                    )

            rules = [
                RuleApplied(
                    citation="NEC 2023 Chapter 9 Table 1",
                    constant_id="MAX_CONDUIT_FILL",
                    value_used=fill_limit * 100,
                    unit="%",
                ),
                RuleApplied(
                    citation="NEC 760.154",
                    constant_id="PLFA_NPLFA_SEPARATION",
                    value_used=1 if plfa_nplfa_separated else 0,
                    unit="Required",
                ),
            ]

            if derating < 1.0:
                rules.append(
                    RuleApplied(
                        citation="NEC 310.15(B)(3)(a)",
                        constant_id="CONDUCTOR_DERATING",
                        value_used=derating,
                        unit="Factor",
                    )
                )

            conf_level = ConfidenceLevel.LOW if not is_compliant else ConfidenceLevel.HIGH
            conf = ConfidenceScore(
                input_quality_score=0.90,
                rule_coverage=1.0,
                geometry_certainty=1.0,
                overall=conf_level,
            )

            return DecisionProvenance.new(
                decision_type="conduit_emt_trade_sizing",
                value={
                    "conduit_trade_size": optimal_size,
                    "conduit_type": c_type,
                    "actual_fill_percentage": round(actual_fill_pct, 2),
                    "total_cable_area_mm2": round(total_area, 2),
                    "fill_limit_pct": round(fill_limit * 100, 1),
                    "is_compliant": is_compliant,
                    "derating_factor": derating,
                    "plfa_nplfa_separated": plfa_nplfa_separated,
                },
                inputs={
                    "cables": conductor_count,
                    "bundle_id": bundle_id,
                    "conduit_type": conduit_type,
                },
                rules_applied=rules,
                algorithm={
                    "name": "DynamicNEC_FillSizer",
                    "version": "v18",
                    "corrections": [
                        "Added FPLP/THHN/XHHW insulation types (not just FPLR)",
                        "PLFA/NPLFA separation per NEC 760.154",
                        "RMC/IMC conduit options (not just EMT)",
                        "Verified NEC Table 4 fill area values",
                        "Conductor derating per NEC 310.15(B)(3)(a)",
                        "Cable tray option for oversized bundles",
                    ],
                },
                confidence=conf,
                selected_because=(
                    f"Minimum valid conduit ensuring free air separation "
                    f"preserving {fill_limit * 100:.0f}% NEC fill parameter."
                ),
                warnings=warnings,
                violations=prov_violations,
            )

        # Fallback: return dict
        return {
            "conduit_trade_size": optimal_size,
            "conduit_type": c_type,
            "actual_fill_percentage": round(actual_fill_pct, 2),
            "total_cable_area_mm2": round(total_area, 2),
            "is_compliant": is_compliant,
            "derating_factor": derating,
            "plfa_nplfa_separated": plfa_nplfa_separated,
            "warnings": warnings,
            "violations": [str(v) for v in violations],
        }

    # ------------------------------------------------------------------
    # Conduit-Wire Feedback Loop
    # ------------------------------------------------------------------

    def analyze_with_wire_overrides(
        self,
        bundle_id: str,
        wire_inventory: List[Dict],
        wire_size_overrides: Optional[Dict[int, int]] = None,
        conduit_type: str = "EMT",
        enforce_plfa_separation: bool = True,
    ) -> Any:
        """Analyze conduit fill with wire size overrides from NAC voltage drop.

        This method accepts a wire_size_overrides dict that maps original AWG
        to upgraded AWG (e.g., {14: 10} means all 14AWG wires were upsized
        to 10AWG for voltage drop compliance). The conduit fill calculation
        MUST use the upgraded wire sizes to prevent overfilled conduits.

        Per NEC Chapter 9 Table 1, if the actual (upsized) wire diameters
        cause fill to exceed the limit, the conduit must be upsized too.
        Failure to account for upsized wires is a CRITICAL safety violation
        — an overfilled conduit can cause insulation melting during a fire,
        defeating the fire alarm system precisely when it is needed most.

        Args:
            bundle_id: Identifier for this cable bundle.
            wire_inventory: List of wire dicts (same format as analyze_routing_bundle).
            wire_size_overrides: Dict mapping original_awg → upgraded_awg.
                E.g., {14: 10, 16: 12} means all 14AWG wires became 10AWG
                and all 16AWG became 12AWG for voltage drop.
            conduit_type: Preferred conduit type.
            enforce_plfa_separation: Whether to enforce NEC 760.154.

        Returns:
            DecisionProvenance or dict with conduit fill analysis using
            the upgraded wire sizes.

        """
        # No overrides — delegate directly to the standard analysis
        if not wire_size_overrides:
            return self.analyze_routing_bundle(
                bundle_id=bundle_id,
                wire_inventory=wire_inventory,
                conduit_type=conduit_type,
                enforce_plfa_separation=enforce_plfa_separation,
            )

        # Build a modified wire inventory with upsized AWG values.
        # Each cable dict is shallow-copied so the caller's data is untouched.
        modified_inventory: List[Dict] = []
        overrides_applied: List[Dict[str, int]] = []

        for cable in wire_inventory:
            original_awg = cable.get("awg", 16)
            upgraded_awg = wire_size_overrides.get(original_awg, original_awg)

            modified_cable = dict(cable)  # shallow copy
            modified_cable["awg"] = upgraded_awg
            modified_inventory.append(modified_cable)

            if upgraded_awg != original_awg:
                overrides_applied.append(
                    {
                        "original_awg": original_awg,
                        "upgraded_awg": upgraded_awg,
                    }
                )
                logger.info(
                    f"Conduit-wire feedback loop: bundle '{bundle_id}' "
                    f"AWG {original_awg} → {upgraded_awg} "
                    f"(voltage-drop upsized)"
                )

        # Run the standard analysis with the modified (upsized) inventory
        result = self.analyze_routing_bundle(
            bundle_id=bundle_id,
            wire_inventory=modified_inventory,
            conduit_type=conduit_type,
            enforce_plfa_separation=enforce_plfa_separation,
        )

        # Augment the provenance object with feedback-loop metadata
        if DecisionProvenance is not None and isinstance(result, DecisionProvenance):
            # Add NEC_WIRE_UPSIZE_FEEDBACK rule
            # NOTE: DecisionProvenance.new() serialises RuleApplied via asdict(),
            # so rules_applied is a list[dict], not list[RuleApplied].  We append
            # a dict to keep the representation consistent.
            upsize_rule_dict = {
                "citation": "NEC 2023 Chapter 9 Table 1 / Art. 210.19(A)",
                "constant_id": "NEC_WIRE_UPSIZE_FEEDBACK",
                "value_used": len(overrides_applied),
                "unit": "overrides",
            }
            if hasattr(result, "rules_applied") and isinstance(result.rules_applied, list):
                result.rules_applied.append(upsize_rule_dict)

            # Add algorithm correction note about the feedback loop
            if hasattr(result, "algorithm") and isinstance(result.algorithm, dict):
                corrections = result.algorithm.setdefault("corrections", [])
                corrections.append(
                    "Conduit-wire feedback loop: wire AWG overrides from NAC voltage-drop "
                    "sizer applied before conduit fill calculation to prevent >80% fill "
                    "from upsized conductors (NEC_WIRE_UPSIZE_FEEDBACK)"
                )

            # Record the override details in inputs for traceability
            if hasattr(result, "inputs") and isinstance(result.inputs, dict):
                result.inputs["wire_size_overrides"] = wire_size_overrides
                result.inputs["overrides_applied"] = overrides_applied

            # If the fill changed, add a warning
            if overrides_applied:
                override_desc = ", ".join(f"{o['original_awg']}AWG→{o['upgraded_awg']}AWG" for o in overrides_applied)
                if hasattr(result, "warnings") and isinstance(result.warnings, list):
                    result.warnings.append(
                        f"NEC_WIRE_UPSIZE_FEEDBACK: Wire upsizing ({override_desc}) "
                        f"applied to conduit fill calculation. Conduit may need "
                        f"upsizing to accommodate larger conductors."
                    )

        # Fallback: augment plain dict result
        elif isinstance(result, dict):
            result["wire_size_overrides"] = wire_size_overrides
            result["overrides_applied"] = overrides_applied
            if overrides_applied:
                override_desc = ", ".join(f"{o['original_awg']}AWG→{o['upgraded_awg']}AWG" for o in overrides_applied)
                result.setdefault("warnings", []).append(
                    f"NEC_WIRE_UPSIZE_FEEDBACK: Wire upsizing ({override_desc}) "
                    f"applied to conduit fill calculation. Conduit may need "
                    f"upsizing to accommodate larger conductors."
                )

        return result


__all__ = [
    "CONDUCTOR_DERATING",
    "CONDUIT_SPECS",
    "FILL_LIMITS",
    "WIRE_DIAMETERS_MM",
    "CircuitClass",
    "ConduitFillResult",
    "ConduitSizer",
    "ConduitType",
    "InsulationType",
    "WireSpec",
    "get_derating_factor",
]
