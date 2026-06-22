"""marine/output — Design deliverables: BOM, FAT procedures, commissioning checklist."""
from marine.output.bom_generator import (
    BOMItem, generate_bom_from_detectors, generate_bom_from_divisions,
    generate_bom_from_extinguishing, generate_full_bom,
)
from marine.output.commissioning_checklist import (
    COMMISSIONING_ITEMS, generate_commissioning_checklist,
)
from marine.output.test_procedures import (
    FAT_PROCEDURES, generate_detector_fat, generate_extinguishing_fat,
)

__all__ = [
    "BOMItem",
    "COMMISSIONING_ITEMS",
    "FAT_PROCEDURES",
    "generate_bom_from_detectors",
    "generate_bom_from_divisions",
    "generate_bom_from_extinguishing",
    "generate_commissioning_checklist",
    "generate_detector_fat",
    "generate_extinguishing_fat",
    "generate_full_bom",
]
