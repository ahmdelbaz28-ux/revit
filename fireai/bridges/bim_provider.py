from __future__ import annotations

from typing import Any, Dict, List, Protocol, runtime_checkable


@runtime_checkable
class BIMProvider(Protocol):
    """
    Protocol for BIM data providers.
    Allows the FireAI kernel to remain agnostic of the underlying BIM platform
    (Local Revit, Autodesk Forge, IFC, etc.)
    """

    def get_rooms(self, source: str) -> List[Dict[str, Any]]:
        """Extract room data from the source."""
        ...

    def write_detectors(self, project_id: str, detectors: List[Dict[str, Any]]) -> bool:
        """Write detector placements back to the BIM model."""
        ...

    def get_project_metadata(self, project_id: str) -> Dict[str, Any]:
        """Retrieve metadata about the BIM project."""
        ...


class BIMRoom:
    """Standardized room representation for the FireAI Kernel."""
    def __init__(
        self,
        room_id: str,
        name: str,
        area_m2: float,
        polygon: List[tuple[float, float]],
        ceiling_height: float = 3.0,
        metadata: Dict[str, Any] = None
    ):
        self.room_id = room_id
        self.name = name
        self.area_m2 = area_m2
        self.polygon = polygon
        self.ceiling_height = ceiling_height
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "room_id": self.room_id,
            "name": self.name,
            "area_m2": self.area_m2,
            "polygon": self.polygon,
            "ceiling_height": self.ceiling_height,
            "metadata": self.metadata
        }
