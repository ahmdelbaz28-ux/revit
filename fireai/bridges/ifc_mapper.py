"""ifc_mapper.py — ISO 16739-1:2024 (IFC 4.3) Data Transformer
============================================================
Transforms Revit/AutoCAD internal elements into standardized IFC 4.3 
Representations for cross-platform compliance.
"""

from typing import Any, Dict, List

class IFCMapper:
    """
    Standardized transformer for Fire Safety elements to IFC 4.3 schema.
    Specifically maps IfcSensor (FireSensors) and IfcDistributionControlElement.
    """

    @staticmethod
    def map_to_ifc43(element_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Maps internal dictionary to IFC 4.3 Property Sets.
        """
        category = element_data.get("category", "Unknown")
        
        ifc_obj = {
            "GlobalId": element_data.get("id"),
            "Name": element_data.get("name"),
            "ObjectType": f"FIRE_ALARM_{category.upper()}",
            "PredefinedType": IFCMapper._get_predefined_type(category),
            "ObjectPlacement": {
                "RelativePlacement": {
                    "Location": [element_data.get("x", 0), element_data.get("y", 0), element_data.get("z", 0)]
                }
            },
            "PropertySets": {
                "Pset_SensorTypeFireSensor": {
                    "FireSensorType": element_data.get("type", "SMOKE"),
                    "CoverageRadius": element_data.get("coverage_radius", 6.37)
                }
            }
        }
        return ifc_obj

    @staticmethod
    def _get_predefined_type(category: str) -> str:
        mapping = {
            "Walls": "WALL",
            "Floors": "SLAB",
            "Doors": "DOOR",
            "Windows": "WINDOW",
            "Sensors": "FIRESENSOR"
        }
        return mapping.get(category, "NOTDEFINED")
