"""
adapters/pdf_to_rooms_adapter — PDF wall extraction to FireAI Room adapter.

Bridges the GeometryExtractor (which returns raw wall geometry) to the
workflow engine's Room model. This adapter extracts closed wall loops,
constructs room polygons, and classifies occupancy types.

Safety-critical: Empty rooms = zero fire protection zones = FAILED parse.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class Room:
    """Represents a room extracted from a floor plan."""
    name: str = ""
    polygon: Any = None  # shapely Polygon or None
    occupancy_type: Optional[str] = None
    area: float = 0.0


def extract_rooms_from_walls(
    walls: List[Any],
    pdf_path: str = "",
) -> Tuple[List[Room], Dict[str, Any]]:
    """
    Extract rooms from a list of wall geometry objects.

    Given wall segments (lines/polygons), this function:
    1. Identifies closed loops of walls forming rooms
    2. Constructs polygon geometry for each room
    3. Classifies occupancy type based on room name heuristics
    4. Returns Room objects and a diagnostic report

    Args:
        walls: List of wall geometry objects from GeometryExtractor
        pdf_path: Source PDF file path for diagnostic reporting

    Returns:
        Tuple of (rooms_list, report_dict) where report_dict contains
        status, wall_count, and any processing warnings.
    """
    rooms: List[Room] = []
    report: Dict[str, Any] = {
        "status": "ok",
        "wall_count": len(walls) if walls else 0,
        "warnings": [],
    }

    if not walls:
        report["status"] = "no_walls"
        report["warnings"].append("No wall geometry found in PDF")
        return rooms, report

    try:
        # Attempt to form room polygons from wall segments
        # This is a simplified implementation — production code would use
        # proper polygon reconstruction algorithms
        from shapely.geometry import Polygon, LineString
        from shapely.ops import polygonize

        lines = []
        for wall in walls:
            if hasattr(wall, 'coords'):
                try:
                    lines.append(LineString(wall.coords))
                except Exception:
                    continue
            elif hasattr(wall, 'geom_type'):
                lines.append(wall)

        if lines:
            polygons = list(polygonize(lines))
            for i, poly in enumerate(polygons):
                if poly.is_valid and not poly.is_empty:
                    room_name = f"Room_{i + 1}"
                    occupancy = _classify_occupancy(room_name)
                    rooms.append(Room(
                        name=room_name,
                        polygon=poly,
                        occupancy_type=occupancy,
                        area=poly.area,
                    ))

        if not rooms:
            report["status"] = "no_closed_loops"
            report["warnings"].append(
                "Walls found but no closed room loops could be formed"
            )

    except ImportError:
        report["status"] = "shapely_unavailable"
        report["warnings"].append(
            "Shapely library not available for polygon reconstruction"
        )
        logger.warning("Shapely not available — room extraction limited")
    except Exception as e:
        report["status"] = "error"
        report["warnings"].append(f"Room extraction error: {e}")
        logger.error(f"Room extraction failed: {e}", exc_info=True)

    return rooms, report


def select_safe_detector_type(
    room: Room,
    ceiling_height: float = 3.0,
) -> str:
    """
    Select the safest detector type for a given room.

    Safety-critical decision: Always defaults to the most conservative
    (protective) detector type when uncertain.

    Args:
        room: Room object with area and occupancy info
        ceiling_height: Room ceiling height in meters

    Returns:
        Detector type string: "smoke", "heat", "duct", or "beam"
    """
    # Default to smoke detector (most sensitive, most protective)
    if room.occupancy_type in ("kitchen", "mechanical", "utility"):
        return "heat"
    if room.occupancy_type in ("duct", "hvac"):
        return "duct"
    if ceiling_height > 10.6:  # NFPA 72 §17.7.3.4 projected beam
        return "beam"
    return "smoke"


def _classify_occupancy(room_name: str) -> str:
    """Classify room occupancy type from name heuristics."""
    name_lower = room_name.lower()
    if any(kw in name_lower for kw in ("kitchen", "cook")):
        return "kitchen"
    if any(kw in name_lower for kw in ("mech", "utility", "plant")):
        return "mechanical"
    if any(kw in name_lower for kw in ("office", "work")):
        return "business"
    if any(kw in name_lower for kw in ("corridor", "hall", "lobby")):
        return "corridor"
    if any(kw in name_lower for kw in ("stair", "stairw")):
        return "stairwell"
    return "unknown"
