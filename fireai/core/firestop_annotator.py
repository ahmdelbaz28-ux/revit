"""fireai/core/firestop_annotator.py
=================================
Checks spatial overlap of routing topologies against 2D wall objects,
identifying fire-rated boundary penetrations per IBC Section 714.

Forces correct FireStop indicators onto Modelspace outputs preventing
invalid contracting errors.

Architecture:
  - Accepts fire-rated wall line segments as LineString pairs
  - Uses Shapely intersection testing for exact penetration coordinates
  - Generates DXF callouts on FA-FIRESTOP layer
  - Returns penetration count for BOQ and compliance tracking

Safety:
  - IBC S714: Penetrations in fire-resistance-rated assemblies must
    be firestopped using approved materials and methods.
  - Missing firestopping callouts can lead to unsealed penetrations
    that compromise fire-rated compartmentation.
  - Every penetration point is marked with a diamond symbol and
    "FIRESTOP REQ'D [IBC 714]" text annotation.
"""

from __future__ import annotations

from typing import Any, List, Tuple

try:
    from shapely.geometry import LineString

    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False


class FirestoppingAnnotator:
    """Detects and annotates fire-rated wall penetrations in cable routes.

    Given a set of fire-rated wall line segments and a cable route,
    this class finds all intersection points and generates DXF callouts
    at each penetration location. The callouts use the FA-FIRESTOP layer
    and include both a visual marker (circle + X cross) and a text
    annotation referencing IBC S714.

    Parameters
    ----------
        fire_rated_walls_lines: List of ((x1,y1), (x2,y2)) tuples
            representing fire-rated wall centerlines.

    """

    def __init__(self, fire_rated_walls_lines: List[Tuple[Tuple[float, float], Tuple[float, float]]]):
        # In real integration, wall line strings or full polygon footprints can be stored here
        self.fire_lines = [LineString(fw) for fw in fire_rated_walls_lines] if SHAPELY_AVAILABLE else []

    def locate_penetrations(self, cable_route: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """Find all points where a cable route crosses fire-rated walls.

        Uses Shapely LineString intersection testing for exact coordinate
        computation. Returns both single-point and multi-point intersections.

        Parameters
        ----------
            cable_route: Ordered list of (x, y) waypoints forming the cable path.

        Returns
        -------
            List of (x, y) coordinates where the cable penetrates a fire-rated wall.
            Empty list if no penetrations found or Shapely unavailable.

        """
        if len(cable_route) < 2 or not self.fire_lines:
            return []

        cable_path = LineString(cable_route)
        penetration_coords = []

        for wall in self.fire_lines:
            if cable_path.intersects(wall):
                intersections = cable_path.intersection(wall)
                if intersections.geom_type == "Point":
                    penetration_coords.append((intersections.x, intersections.y))
                elif intersections.geom_type == "MultiPoint":
                    for point in intersections.geoms:
                        penetration_coords.append((point.x, point.y))

        return penetration_coords

    def draft_callouts_to_dxf(self, msp: Any, cable_route: List[Tuple[float, float]]) -> int:
        """Generate firestopping callouts on a DXF modelspace.

        For each penetration point found, draws:
          1. A circle marker (radius 0.4 drawing units)
          2. An X cross through the circle
          3. Text annotation "FIRESTOP REQ'D [IBC 714]"

        All entities are placed on the FA-FIRESTOP layer with color 1 (red).

        Parameters
        ----------
            msp: ezdxf Modelspace object to draw into.
            cable_route: Ordered list of (x, y) waypoints.

        Returns
        -------
            Number of penetration callouts generated (0 if none found).

        """
        penetrations = self.locate_penetrations(cable_route)
        if not penetrations:
            return 0

        for x, y in penetrations:
            msp.add_circle((x, y), radius=0.4, dxfattribs={"layer": "FA-FIRESTOP", "color": 1})
            msp.add_line((x - 0.4, y - 0.4), (x + 0.4, y + 0.4), dxfattribs={"layer": "FA-FIRESTOP", "color": 1})
            msp.add_line((x - 0.4, y + 0.4), (x + 0.4, y - 0.4), dxfattribs={"layer": "FA-FIRESTOP", "color": 1})
            text = msp.add_text(
                "FIRESTOP REQ'D [IBC 714]",
                dxfattribs={"layer": "FA-FIRESTOP", "height": 0.35, "color": 1},
            )
            text.set_placement((x + 0.6, y - 0.2))
        return len(penetrations)
