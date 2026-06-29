"""
marine/integration/revit_exporter.py — Revit Family + Model Generator (JSON-only).

V141.2 HONEST DOCUMENTATION (adversarial audit fix):
Previous versions claimed "Generates .rfa family definitions and .rvt
model placements for marine detectors". This was MISLEADING. This module
generates JSON DICTS describing what a Revit family WOULD contain — it
does NOT produce actual .rfa or .rvt binary files that Revit can open.

What this module ACTUALLY does:
  - generate_revit_family(detector): Returns a Python dict with family
    name, category, parameters, and geometry description. This is a
    JSON-serializable representation, NOT a Revit .rfa file.
  - generate_model_placements(...): Returns a list of placement dicts.
    Again, JSON data — not .rvt binary.

How to use this data in Revit (the REAL workflow):
  1. Call generate_revit_family() to get the family definition dict.
  2. Write a Revit plugin (C# or pythonnet) that reads this JSON and
     calls RevitAPI's FamilyInstance.Create() to actually create the
     family in a Revit document.
  3. OR: import the IFC file produced by fireai/bridges/ifc_pipeline.py
     directly into Revit (Revit has native IFC import).

Why JSON (not .rfa/.rvt):
  - .rfa and .rvt are proprietary binary formats that require Revit's
    API to generate correctly. Generating them without Revit installed
    would require reverse-engineering the format (illegal + fragile).
  - JSON is open, language-agnostic, and can be consumed by any Revit
    plugin, Dynamo script, or external tool.
  - The IFC pipeline (fireai/bridges/ifc_pipeline.py) is the recommended
    path for actual Revit model creation — Revit imports IFC natively.

References:
  - Revit API documentation (Autodesk)
  - IFC 4.3 specification (buildingSMART)
  - pythonnet for Python ↔ .NET interop
"""
from __future__ import annotations

from marine.core.types import DetectorPlacement, FireResistanceSpec


def generate_revit_family(detector: DetectorPlacement) -> dict:
    """Return a Revit family definition (JSON-serializable for OFP)."""
    return {
        "family_name": f"Marine_{detector.detector_type.value}",
        "category": "Fire Alarm Devices",
        "parameters": [
            {"name": "Detector_ID", "type": "Text", "value": detector.detector_id},
            {"name": "Zone_ID", "type": "Text", "value": detector.zone_id},
            {"name": "Coverage_m2", "type": "Number", "value": detector.coverage_m2},
            {"name": "Mounting_Height_m", "type": "Number", "value": detector.mounting_height_m},
            {"name": "Rated_Temp_C", "type": "Number", "value": detector.rated_temp_c or 0},
            {"name": "Standard", "type": "Text", "value": detector.standard_reference},
        ],
        "geometry": {
            "type": "cylinder", "diameter_mm": 100, "height_mm": 50,
        },
        "lod": 300,
    }


def generate_revit_placement(detector: DetectorPlacement) -> dict:
    """Return a Revit placement instance (positioned in model coordinates)."""
    return {
        "family_name": f"Marine_{detector.detector_type.value}",
        "instance_id": detector.detector_id,
        "position_xyz_mm": list(detector.position_xyz_mm),
        "rotation_deg": 0,
    }


def generate_revit_division(spec: FireResistanceSpec) -> dict:
    """Return a Revit wall/floor element for a fire division."""
    return {
        "element_id": spec.division_id,
        "type": "Fire_Rated_Bulkhead" if spec.required_class.value.startswith("A-") else "Non_Combustible_Panel",
        "from_zone": spec.from_zone, "to_zone": spec.to_zone,
        "fire_class": spec.required_class.value,
        "material": spec.material,
        "insulation_material": spec.insulation_material or "none",
        "insulation_thickness_mm": spec.insulation_thickness_mm,
        "standard": spec.standard_reference,
    }


__all__ = [
    "generate_revit_division",
    "generate_revit_family",
    "generate_revit_placement",
]
