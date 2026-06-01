"""
QOMN-FIRE CONDUIT FILL SIZING ENGINE
Reference Standard: NEC 2023 Chapter 9, Table 1 & Table 4.

BUG-19 FIX: Added support for fire alarm cable types (FPLP, FPL, FPLR)
per NEC 760.179. Fire alarm systems require FPLP (Power-Limited Fire Alarm)
or FPL (Fire Alarm) cable types. The original code only supported generic
AWG gauges, rejecting FPLP/FPL/FPLR cables — making it impossible to
size conduit for fire alarm circuits, which is the PRIMARY use case.
"""

from qomn_fire.core.errors import Result, ConduitFillError
from qomn_fire.core.constants import (
    EMT_INTERNAL_AREA_1_2_MM2, EMT_INTERNAL_AREA_3_4_MM2, EMT_INTERNAL_AREA_1_MM2,
    WIRE_AREA_14_AWG_MM2, WIRE_AREA_12_AWG_MM2, WIRE_AREA_10_AWG_MM2,
    NEC_FILL_LIMIT_1_WIRE, NEC_FILL_LIMIT_2_WIRES, NEC_FILL_LIMIT_OVER_2_WIRES
)

# SAFETY FIX (V58): Expanded conduit internal area specifications per NEC Chapter 9 Table 4.
# The original code only supported 3 EMT sizes (1/2", 3/4", 1"). Real fire alarm
# projects commonly require larger conduits for trunk lines and multi-circuit runs.
# A conduit run that cannot be sized will either (a) be forced into a too-small conduit
# (overfill → overheating → fire hazard per NEC 310.15) or (b) fail the pipeline entirely.
# Added: EMT 1-1/4" through 4", plus RMC sizes per NEC Table 4.
# Values from NEC 2023 Chapter 9 Table 4 (over 2 wires: 40% fill column).
CONDUIT_INTERNAL_AREAS_MM2 = {
    # EMT (Electrical Metallic Tubing) — NEC Table 4, Article 358
    "EMT 1/2": 196.1,
    "EMT 3/4": 343.9,
    "EMT 1": 557.4,
    "EMT 1-1/4": 952.1,
    "EMT 1-1/2": 1308.0,
    "EMT 2": 2110.0,
    "EMT 2-1/2": 3150.0,
    "EMT 3": 4680.0,
    "EMT 3-1/2": 5910.0,
    "EMT 4": 7620.0,
    # RMC (Rigid Metal Conduit) — NEC Table 4, Article 344
    "RMC 1/2": 143.8,
    "RMC 3/4": 262.4,
    "RMC 1": 437.5,
    "RMC 1-1/4": 792.6,
    "RMC 1-1/2": 1100.0,
    "RMC 2": 1780.0,
    "RMC 2-1/2": 2760.0,
    "RMC 3": 4240.0,
    "RMC 3-1/2": 5420.0,
    "RMC 4": 7150.0,
}

# BUG-19 FIX: Fire alarm cable cross-sectional areas (NEC Chapter 9, Table 5A)
# FPLP = Power-Limited Fire Alarm Cable (NEC 760.179)
# FPL = Fire Alarm Cable (NEC 760.179)
# FPLR = Riser-Rated Fire Alarm Cable (NEC 760.179(B))
# These are the standard cable types for fire alarm systems.
# Values from NEC Chapter 9 Table 5A — approximate for typical 2-conductor cables.
FIRE_ALARM_CABLE_AREAS = {
    "FPLP 14": 6.26,    # FPLP 14 AWG 2-conductor ≈ same as 14 AWG THHN
    "FPLP 12": 8.58,    # FPLP 12 AWG 2-conductor
    "FPLP 10": 13.61,   # FPLP 10 AWG 2-conductor
    "FPL 14": 6.26,     # FPL 14 AWG 2-conductor
    "FPL 12": 8.58,     # FPL 12 AWG 2-conductor
    "FPL 10": 13.61,    # FPL 10 AWG 2-conductor
    "FPLR 14": 6.26,    # FPLR 14 AWG 2-conductor
    "FPLR 12": 8.58,    # FPLR 12 AWG 2-conductor
    "FPLR 10": 13.61,   # FPLR 10 AWG 2-conductor
    # Standard THHN/THWN building wire (NEC Table 5)
    "THHN 14": 6.26,
    "THHN 12": 8.58,
    "THHN 10": 13.61,
    "THWN 14": 6.26,
    "THWN 12": 8.58,
    "THWN 10": 13.61,
}

def calculate_conduit_fill(
    conduit_size: str,
    wire_gauge: str,
    wire_count: int,
    conduit_type: str = "EMT"
) -> Result[float, ConduitFillError]:
    """
    Calculate conduit fill ratio per NEC Chapter 9 Table 1.

    SAFETY FIX (V58): Added conduit_type parameter and expanded size support.
    Per NEC 760, fire alarm circuits commonly use EMT and RMC conduits.
    The original code only supported 3 EMT sizes, which was insufficient
    for real projects with multi-circuit trunk lines.

    Args:
        conduit_size: Trade size (e.g., "1/2", "3/4", "1", "1-1/4", "1-1/2", "2")
        wire_gauge: Wire/cable type (e.g., "14 AWG", "FPLP 14", "THHN 12")
        wire_count: Number of conductors in the conduit
        conduit_type: Conduit type ("EMT" or "RMC") — default EMT per NEC 760
    """
    import math

    if wire_count <= 0:
        return Result(error=ConduitFillError(
            message="Wire count must be a positive integer.",
            code_ref="NEC Ch.9 Table 1",
            remedy="Increase wire count parameter above zero."
        ))

    # BUG-F1 FIX: Removed math.isfinite(wire_count) — Python int is ALWAYS finite.
    # math.isfinite() only returns False for float NaN and Inf, which cannot occur
    # for int types. The check was dead code that provided zero protection.
    # Instead, validate that wire_count is actually an integer type.
    if not isinstance(wire_count, int):
        return Result(error=ConduitFillError(
            message=f"Wire count must be an integer, got {type(wire_count).__name__}.",
            code_ref="NEC Ch.9 Table 1",
            remedy="Provide an integer wire count."
        ))

    conduit_area = 0.0

    # Try expanded conduit area lookup first
    conduit_key = f"{conduit_type.upper()} {conduit_size}"
    if conduit_key in CONDUIT_INTERNAL_AREAS_MM2:
        conduit_area = CONDUIT_INTERNAL_AREAS_MM2[conduit_key]
    # Backward compatibility: bare size string defaults to EMT
    elif conduit_size == "1/2":
        conduit_area = EMT_INTERNAL_AREA_1_2_MM2
    elif conduit_size == "3/4":
        conduit_area = EMT_INTERNAL_AREA_3_4_MM2
    elif conduit_size == "1":
        conduit_area = EMT_INTERNAL_AREA_1_MM2
    else:
        supported_sizes = sorted(set(
            k.split(" ", 1)[1] for k in CONDUIT_INTERNAL_AREAS_MM2.keys()
        ))
        return Result(error=ConduitFillError(
            message=f"Unsupported conduit size '{conduit_size}' for type '{conduit_type}'.",
            code_ref="NEC Table 4",
            remedy=f"Use standard trade sizes: {', '.join(supported_sizes)}. "
                   f"Supported types: EMT, RMC."
        ))

    # BUG-19 FIX: Support fire alarm cable types (FPLP, FPL, FPLR) and
    # standard building wire (THHN, THWN) in addition to generic AWG.
    wire_area = 0.0
    if wire_gauge in FIRE_ALARM_CABLE_AREAS:
        wire_area = FIRE_ALARM_CABLE_AREAS[wire_gauge]
    elif wire_gauge == "14 AWG":
        wire_area = WIRE_AREA_14_AWG_MM2
    elif wire_gauge == "12 AWG":
        wire_area = WIRE_AREA_12_AWG_MM2
    elif wire_gauge == "10 AWG":
        wire_area = WIRE_AREA_10_AWG_MM2
    else:
        supported = ", ".join(sorted(set(
            list(FIRE_ALARM_CABLE_AREAS.keys()) + ["14 AWG", "12 AWG", "10 AWG"]
        )))
        return Result(error=ConduitFillError(
            message=f"Unsupported wire/cable type '{wire_gauge}'",
            code_ref="NEC Table 5/5A",
            remedy=f"Select a compliant wire/cable type. Supported: {supported}"
        ))

    total_wire_area = wire_area * wire_count
    fill_ratio = total_wire_area / conduit_area

    if wire_count == 1:
        limit = NEC_FILL_LIMIT_1_WIRE
    elif wire_count == 2:
        limit = NEC_FILL_LIMIT_2_WIRES
    else:
        limit = NEC_FILL_LIMIT_OVER_2_WIRES

    if fill_ratio > limit:
        return Result(error=ConduitFillError(
            message=f"Conduit fill exceeds permissible NEC threshold limit: {fill_ratio:.2%} > {limit:.2%}",
            code_ref="NEC Ch.9 Table 1",
            remedy="Upsize conduit selection or reduce wire run count."
        ))

    return Result(value=fill_ratio)
