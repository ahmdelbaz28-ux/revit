"""
QOMN-FIRE CONDUIT FILL SIZING ENGINE
Reference Standard: NEC 2023 Chapter 9, Table 1 & Table 4.
"""

from qomn_fire.core.errors import Result, ConduitFillError
from qomn_fire.core.constants import (
    EMT_INTERNAL_AREA_1_2_MM2, EMT_INTERNAL_AREA_3_4_MM2, EMT_INTERNAL_AREA_1_MM2,
    WIRE_AREA_14_AWG_MM2, WIRE_AREA_12_AWG_MM2, WIRE_AREA_10_AWG_MM2,
    NEC_FILL_LIMIT_1_WIRE, NEC_FILL_LIMIT_2_WIRES, NEC_FILL_LIMIT_OVER_2_WIRES
)

def calculate_conduit_fill(conduit_size: str, wire_gauge: str, wire_count: int) -> Result[float, ConduitFillError]:
    if wire_count <= 0:
        return Result(error=ConduitFillError(
            message="Wire count must be a positive integer.",
            code_ref="NEC Ch.9 Table 1",
            remedy="Increase wire count parameter above zero."
        ))

    conduit_area = 0.0
    if conduit_size == "1/2":
        conduit_area = EMT_INTERNAL_AREA_1_2_MM2
    elif conduit_size == "3/4":
        conduit_area = EMT_INTERNAL_AREA_3_4_MM2
    elif conduit_size == "1":
        conduit_area = EMT_INTERNAL_AREA_1_MM2
    else:
        return Result(error=ConduitFillError(
            message=f"Unsupported trade conduit size '{conduit_size}'",
            code_ref="NEC Table 4",
            remedy="Use standard sizes: '1/2', '3/4', or '1'."
        ))

    wire_area = 0.0
    if wire_gauge == "14 AWG":
        wire_area = WIRE_AREA_14_AWG_MM2
    elif wire_gauge == "12 AWG":
        wire_area = WIRE_AREA_12_AWG_MM2
    elif wire_gauge == "10 AWG":
        wire_area = WIRE_AREA_10_AWG_MM2
    else:
        return Result(error=ConduitFillError(
            message=f"Unsupported AWG gauge '{wire_gauge}'",
            code_ref="NEC Table 5",
            remedy="Select compliant wire gauge: '14 AWG', '12 AWG', or '10 AWG'."
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
        return Result(
            value=fill_ratio,
            error=ConduitFillError(
                message=f"Conduit fill exceeds permissible NEC threshold limit: {fill_ratio:.2%} > {limit:.2%}",
                code_ref="NEC Ch.9 Table 1",
                remedy="Upsize conduit selection or reduce wire run count."
            )
        )

    return Result(value=fill_ratio)
