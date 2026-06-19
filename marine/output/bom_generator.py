"""marine/output/bom_generator.py — Bill of Materials generator for marine fire systems.

Generates a structured BOM from detector placements, extinguishing designs,
and fire-division specs. Suitable for export to procurement / ERP systems.
"""
from __future__ import annotations

from typing import Dict, List

from marine.core.types import DetectorPlacement, ExtinguishingDesign, FireResistanceSpec


class BOMItem:
    """Single line item in a marine fire-safety BOM."""

    def __init__(
        self,
        item_id: str,
        description: str,
        quantity: float,
        unit: str,
        standard_reference: str = "",
    ):
        self.item_id = item_id
        self.description = description
        self.quantity = quantity
        self.unit = unit
        self.standard_reference = standard_reference

    def to_dict(self) -> Dict[str, str | float]:
        return {
            "item_id": self.item_id,
            "description": self.description,
            "quantity": self.quantity,
            "unit": self.unit,
            "standard_reference": self.standard_reference,
        }


def generate_bom_from_detectors(
    placements: List[DetectorPlacement],
) -> List[Dict[str, str | float]]:
    """Generate BOM items grouped by detector type."""
    counts: Dict[str, int] = {}
    for p in placements:
        counts[p.detector_type.value] = counts.get(p.detector_type.value, 0) + 1

    bom: List[Dict[str, str | float]] = []
    for dtype, qty in counts.items():
        bom.append(
            BOMItem(
                item_id=f"DET-{dtype.upper()}",
                description=f"Marine fire detector ({dtype})",
                quantity=qty,
                unit="ea",
                standard_reference="IEC 60092-502 §4",
            ).to_dict()
        )
    return bom


def generate_bom_from_extinguishing(
    designs: List[ExtinguishingDesign],
) -> List[Dict[str, str | float]]:
    """Generate BOM items for extinguishing systems."""
    bom: List[Dict[str, str | float]] = []
    for d in designs:
        bom.append(
            BOMItem(
                item_id=f"EXT-{d.system_type.value.upper()}",
                description=f"Fixed {d.system_type.value} extinguishing system",
                quantity=d.nozzles,
                unit="nozzle",
                standard_reference=d.standard_reference,
            ).to_dict()
        )
        if d.agent_quantity_kg > 0:
            bom.append(
                BOMItem(
                    item_id=f"AGENT-{d.system_type.value.upper()}",
                    description=f"Extinguishing agent ({d.system_type.value})",
                    quantity=d.agent_quantity_kg,
                    unit="kg",
                    standard_reference=d.standard_reference,
                ).to_dict()
            )
        if d.pipe_length_m > 0:
            bom.append(
                BOMItem(
                    item_id=f"PIPE-{d.system_type.value.upper()}",
                    description=f"Fire-resistant piping ({d.system_type.value})",
                    quantity=d.pipe_length_m,
                    unit="m",
                    standard_reference=d.standard_reference,
                ).to_dict()
            )
    return bom


def generate_bom_from_divisions(
    specs: List[FireResistanceSpec],
) -> List[Dict[str, str | float]]:
    """Generate BOM items for fire-division materials."""
    bom: List[Dict[str, str | float]] = []
    for s in specs:
        if s.insulation_material and s.insulation_material != "none":
            bom.append(
                BOMItem(
                    item_id=f"INS-{s.required_class.value}",
                    description=f"Insulation for {s.required_class.value} division",
                    quantity=s.insulation_thickness_mm,
                    unit="mm",
                    standard_reference=s.standard_reference,
                ).to_dict()
            )
    return bom


def generate_full_bom(
    placements: List[DetectorPlacement],
    designs: List[ExtinguishingDesign],
    specs: List[FireResistanceSpec],
) -> Dict[str, List[Dict[str, str | float]]]:
    """Generate the complete BOM for a marine fire-safety design."""
    return {
        "detectors": generate_bom_from_detectors(placements),
        "extinguishing": generate_bom_from_extinguishing(designs),
        "divisions": generate_bom_from_divisions(specs),
    }


__all__ = [
    "BOMItem",
    "generate_bom_from_detectors",
    "generate_bom_from_extinguishing",
    "generate_bom_from_divisions",
    "generate_full_bom",
]
