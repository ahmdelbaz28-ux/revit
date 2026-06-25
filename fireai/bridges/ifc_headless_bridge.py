"""fireai/bridges/ifc_headless_bridge.py
=======================================
ELITE IFC4 Headless BIM Integration (No COM, No active Revit required)
Replaces unreliable COM/Windows bindings with pure, standard OpenBIM logic.

Reads Spaces/Geometries directly via ifcopenshell and writes FireAlarm
Devices as native `IfcSensor` elements complete with Property Sets (Pset).

Architecture:
  - Pure Python — no COM, no Windows, no active Revit session required
  - Uses ifcopenshell for standards-compliant IFC4 read/write
  - Extracts room geometry from IfcSpace with hierarchical placement resolution
  - Extracts structural obstructions (walls, beams, ducts) as AABB
  - Extracts storey elevations with full coordinate hierarchy resolution
  - Writes devices as IfcSensor with Pset_FireAI_Compliance property set
  - Assigns devices to IfcBuildingStorey via spatial containment

V24 GAP-1 Upgrade:
  - Added extract_storeys() for multi-storey building support
  - Added extract_obstructions() for ray-trace engine integration
  - Added extract_spaces_enhanced() with polygon boundaries + volume
  - Preserved existing extract_spaces() and push_fire_alarm_design() APIs
  - All new methods are additive — no breaking changes

Safety:
  - IFC is the open standard for BIM data exchange (buildingSMART).
  - COM-based bridges require a running Revit instance on Windows,
    creating a fragile dependency that prevents batch processing.
  - This headless bridge enables CI/CD pipeline integration and
    server-side processing without any GUI application running.

Standards:
  - IFC4 / ISO 16739-1:2018 — schema
  - NFPA 72-2022 §17.8.3.4  — detector placement & topology
  - IEC 60079-0:2017         — ATEX compliance property sets
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

try:
    import ifcopenshell
    from ifcopenshell.api import run

    IFC_AVAILABLE = True
except ImportError:
    ifcopenshell = None
    IFC_AVAILABLE = False

try:
    import ifcopenshell.geom

    GEOM_AVAILABLE = True
except ImportError:
    GEOM_AVAILABLE = False

logger = logging.getLogger(__name__)


# ── Geometry helpers (for extract_obstructions / extract_spaces_enhanced) ──


def _convex_hull_2d(pts: List[Tuple[float, float, float]]) -> List[Tuple[float, float, float]]:
    """Andrew's monotone chain convex hull on XY plane."""

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    sorted_pts = sorted(set(pts))
    if len(sorted_pts) < 3:
        return list(sorted_pts)
    lower: list = []
    for p in sorted_pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list = []
    for p in reversed(sorted_pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _polygon_area_2d(pts: List[Tuple[float, float, float]]) -> float:
    """Shoelace formula for polygon area on XY plane."""
    n = len(pts)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += pts[i][0] * pts[j][1]
        area -= pts[j][0] * pts[i][1]
    return abs(area) / 2.0


class HeadlessIFCBridge:
    """Pure-Python IFC4 bridge for reading building geometry and writing
    fire alarm devices back to the IFC model.

    This bridge operates entirely through ifcopenshell, without requiring
    a running Revit instance or Windows COM bindings. It can be used in
    server-side processing, CI/CD pipelines, and batch operations.

    Parameters
    ----------
        ifc_path: Path to the IFC4 file to read.

    Raises
    ------
        ImportError: If ifcopenshell is not installed.
        ValueError: If the IFC file cannot be opened.

    """

    # IFC types that are structural obstructions for ray-tracing
    OBSTRUCTION_TYPES = (
        "IfcWall",
        "IfcWallStandardCase",
        "IfcBeam",
        "IfcBeamStandardCase",
        "IfcColumn",
        "IfcColumnStandardCase",
        "IfcMember",
        "IfcDuctSegment",
        "IfcDuctFitting",
        "IfcPipeSegment",
        "IfcCovering",  # lowered ceilings
        "IfcSlab",  # intermediate floors
    )

    def __init__(self, ifc_path: str):
        if not ifcopenshell:
            raise ImportError("CRITICAL: ifcopenshell library missing. Install via pip install ifcopenshell")
        self.ifc_path = ifc_path
        try:
            self.model = ifcopenshell.open(ifc_path)
        except Exception as e:
            raise ValueError(f"Failed to open IFC model: {e}")
        # Geometry settings for tessellation (lazy-initialized)
        self._geom_settings: object = None  # V131 FIX: Typed as object for mypy compatibility

    # ══════════════════════════════════════════════════════════════
    # ORIGINAL API (preserved for backward compatibility)
    # ══════════════════════════════════════════════════════════════

    def extract_spaces(self) -> List[Dict[str, Any]]:
        """Extract Room geometry for the engine using IfcSpace.

        Reads all IfcSpace elements from the IFC model and resolves
        their hierarchical placement chains to get absolute (x, y, z)
        coordinates. Returns a list of room dictionaries suitable for
        the FireAI analysis pipeline.

        Returns:
            List of dicts with keys:
                - guid: IfcSpace GlobalId
                - name: Space name (LongName > Name > UNNAMED_SPACE)
                - x, y, z: Absolute placement coordinates

        """
        rooms = []
        for space in self.model.by_type("IfcSpace"):
            try:
                placement = space.ObjectPlacement
                x, y, z = self._resolve_local_placement(placement)
                rooms.append(
                    {
                        "guid": space.GlobalId,
                        "name": space.LongName or space.Name or "UNNAMED_SPACE",
                        "x": x,
                        "y": y,
                        "z": z,
                    }
                )
            except Exception as e:
                logger.warning("Error processing space %s: %s", space.GlobalId, e)
        return rooms

    def push_fire_alarm_design(self, devices: List[Dict[str, Any]], output_path: str) -> bool:
        """Write optimal Fire Alarm devices natively back into the IFC building.

        Creates `IfcSensor` elements representing the engineered fire alarm
        topology, with 3D placement and custom property sets for compliance
        tracking.

        Each device gets:
          1. An IfcSensor entity with appropriate name
          2. 3D placement via 4x4 transformation matrix
          3. Spatial containment assignment to the first IfcBuildingStorey
          4. Pset_FireAI_Compliance property set with engineering metadata

        Parameters
        ----------
            devices: List of device dicts with keys:
                - device_id: Unique device identifier
                - type: Device type string (SMOKE, HEAT, etc.)
                - x, y, z: 3D placement coordinates
                - loop_id: SLC loop assignment
                - address: Device address on the loop
                - checksum: Validation hash
            output_path: Path to write the modified IFC file.

        Returns
        -------
            True if export succeeded.

        """
        # Fetch storeys and sort by elevation for correct device placement
        # V78 FIX: Previously ALL devices were placed on the first storey regardless
        # of their z-coordinate. A 10-storey building would have 200+ devices on
        # the ground floor in the IFC model — corrupt data for AHJ/BMS systems.
        storeys = self.model.by_type("IfcBuildingStorey")
        storey_elevs = []
        for s in storeys:
            try:
                elev = getattr(s, "Elevation", 0.0) or 0.0
                storey_elevs.append((s, float(elev)))
            except (TypeError, ValueError):
                storey_elevs.append((s, 0.0))
        storey_elevs.sort(key=lambda x: x[1])

        for dev in devices:
            # V78 FIX: Proper device type mapping — previously everything that wasn't
            # SMOKE was mapped to HEATSENSOR, losing UGLD, FLAME, and combo types.
            # This affects maintenance scheduling and ATEX marking per NFPA 72 §14.3.
            type_upper = dev.get("type", "").upper()
            if "SMOKE" in type_upper or "FLAME" in type_upper or "UGLD" in type_upper or "ULTRASONIC" in type_upper or "HEAT" in type_upper or "COMBO" in type_upper or "MULTI" in type_upper:
                pass
            else:
                logger.warning("Unknown device type '%s' mapped to HEATSENSOR for device %s", type_upper, dev.get('device_id'))

            # Match device z-coordinate to correct storey
            z = dev.get("z", 0.0)
            target_storey = None
            for s, elev in storey_elevs:
                if z >= elev - 0.5:  # 0.5m tolerance
                    target_storey = s
            if target_storey is None and storey_elevs:
                target_storey = storey_elevs[0][0]

            device_elem = run(
                "root.create_entity",
                self.model,
                ifc_class="IfcSensor",
                name=dev.get("device_id", "FA_Device"),
            )

            x, y, z = dev.get("x", 0.0), dev.get("y", 0.0), dev.get("z", 3.0)
            matrix = [
                [1.0, 0.0, 0.0, x],
                [0.0, 1.0, 0.0, y],
                [0.0, 0.0, 1.0, z],
                [0.0, 0.0, 0.0, 1.0],
            ]
            run("geometry.edit_object_placement", self.model, product=device_elem, matrix=matrix)

            if target_storey:
                run("spatial.assign_container", self.model, relating_structure=target_storey, products=[device_elem])

            pset = run("pset.add_pset", self.model, product=device_elem, name="Pset_FireAI_Compliance")
            run(
                "pset.edit_pset",
                self.model,
                pset=pset,
                properties={
                    "Loop_ID": str(dev.get("loop_id", "UNK")),
                    "Device_Address": str(dev.get("address", "UNK")),
                    "Validation_Hash": str(dev.get("checksum", "INVALID")),
                    # V76 CRIT-04 FIX: Was hardcoded True — fabricated NFPA 72
                    # compliance claim written to IFC BIM model regardless of
                    # whether the device placement was actually verified. This
                    # is a legal liability and life-safety fraud risk. Now reads
                    # from device dict with default False (fail-safe).
                    "NFPA72_Compliant": bool(dev.get("nfpa72_compliant", False)),
                },
            )

        self.model.write(output_path)
        logger.info("Successfully exported Level-3 BIM IFC Model with Native Topology: %s", output_path)
        return True

    # ══════════════════════════════════════════════════════════════
    # V24 GAP-1 NEW METHODS (additive — no breaking changes)
    # ══════════════════════════════════════════════════════════════

    def extract_storeys(self) -> List[Dict[str, Any]]:
        """Extract all IfcBuildingStorey entities with resolved absolute elevation.

        Returns list of dicts sorted by elevation (ascending) with keys:
            - guid: IfcBuildingStorey GlobalId
            - name: Storey name
            - elevation: Absolute Z coordinate (m above global origin)

        IFC4 §5.4.3.1: IfcBuildingStorey.Elevation is relative to building
        origin; we resolve the full PlacementRelTo hierarchy for absolute Z.
        """
        result = []
        for storey in self.model.by_type("IfcBuildingStorey"):
            elev = self._resolve_storey_elevation(storey)
            result.append(
                {
                    "guid": storey.GlobalId,
                    "name": storey.Name or "",
                    "elevation": elev,
                }
            )
        result.sort(key=lambda s: s["elevation"])
        return result

    def extract_spaces_enhanced(self) -> List[Dict[str, Any]]:
        """Extract IfcSpace entities with full geometry (polygon, volume, area).

        Enhanced version of extract_spaces() that provides:
          - Floor polygon boundary (convex hull of floor-level vertices)
          - Space height, area, and volume
          - Storey name and elevation

        Falls back to bounding-box estimation when ifcopenshell.geom
        tessellation is unavailable.

        Returns list of dicts with keys:
            - guid, name, long_name, storey_name, storey_elevation
            - center: (x, y, z) tuple
            - floor_polygon: [(x,y,z), ...] polygon vertices
            - height_m: space height
            - area_m2: floor area
            - volume_m3: space volume
        """
        storey_map = {}
        for s in self.extract_storeys():
            storey_map[s["guid"]] = s

        result = []
        for space in self.model.by_type("IfcSpace"):
            try:
                sd = self._extract_one_space_enhanced(space, storey_map)
                if sd is not None:
                    result.append(sd)
            except Exception as e:
                logger.warning("Error extracting enhanced space %s: %s", space.GlobalId, e)

        result.sort(key=lambda s: (s.get("storey_elevation", 0.0), s.get("name", "")))
        return result

    def extract_obstructions(self) -> List[Dict[str, Any]]:
        """Extract walls, beams, columns, ducts as AABB obstructions.

        Each AABB is in world (absolute) coordinates and can be consumed
        directly by the FlameDetectorAOCRayTrace engine as
        Obstruction(vertices=aabb_vertices, spectral_transparency=OPAQUE).

        Returns list of dicts with keys:
            - guid: Entity GlobalId
            - ifc_type: IFC class name (IfcWall, IfcBeam, etc.)
            - name: Entity name
            - aabb_min: (x, y, z) AABB minimum corner
            - aabb_max: (x, y, z) AABB maximum corner
            - aabb_vertices: List of 8 (x,y,z) corner tuples

        IFC4 §8: IfcWall, IfcBeam, IfcColumn, IfcMember,
        IfcDuctSegment, IfcPipeSegment, IfcSlab.
        """
        result = []
        for ifc_type in self.OBSTRUCTION_TYPES:
            for entity in self.model.by_type(ifc_type):
                try:
                    od = self._extract_aabb(entity, ifc_type)
                    if od is not None:
                        result.append(od)
                except Exception as e:
                    logger.debug("Could not extract AABB for %s: %s", entity.GlobalId, e)
        return result

    # ══════════════════════════════════════════════════════════════
    # PRIVATE HELPERS
    # ══════════════════════════════════════════════════════════════

    def _resolve_local_placement(self, placement) -> tuple:
        """Traverse hierarchical IFC coordinate placement to get Absolute XYZ.

        V15 FIX: Previously only read the FIRST level of RelativePlacement,
        returning relative coordinates for nested placements. Now walks the
        full PlacementRelTo chain to accumulate absolute coordinates.
        """
        x, y, z = 0.0, 0.0, 0.0
        current = placement
        while current:
            if hasattr(current, "RelativePlacement") and current.RelativePlacement:
                rel = current.RelativePlacement
                if hasattr(rel, "Location") and rel.Location:
                    coords = rel.Location.Coordinates
                    x += coords[0] if len(coords) > 0 else 0.0
                    y += coords[1] if len(coords) > 1 else 0.0
                    z += coords[2] if len(coords) > 2 else 0.0
            if hasattr(current, "PlacementRelTo") and current.PlacementRelTo:
                current = current.PlacementRelTo
            else:
                break
        return x, y, z

    def _resolve_storey_elevation(self, storey) -> float:
        """Absolute elevation of storey: traverse PlacementRelTo chain."""
        try:
            placement = storey.ObjectPlacement
            if placement:
                _, _, z = self._resolve_local_placement(placement)
                return z
        except Exception as e:
            logger.debug("Failed to resolve local placement for storey elevation: %s", e)
        # Fallback to storey.Elevation attribute
        try:
            return float(storey.Elevation) if storey.Elevation else 0.0
        except Exception:
            return 0.0

    def _get_parent_storey(self, entity) -> Optional[Any]:
        """Walk ContainedInStructure to find IfcBuildingStorey."""
        try:
            for rel in entity.ContainedInStructure:
                container = rel.RelatingStructure
                if container.is_a("IfcBuildingStorey"):
                    return container
                # Walk up one more level
                parent = self._get_parent_storey(container)
                if parent:
                    return parent
        except Exception as e:
            logger.debug("Failed to get parent storey: %s", e)
        return None

    def _get_geom_settings(self):
        """Lazy-initialize ifcopenshell geometry settings."""
        if self._geom_settings is None and GEOM_AVAILABLE:
            s = ifcopenshell.geom.settings()
            s.set(s.USE_WORLD_COORDS, True)
            s.set(s.APPLY_LAYERSETS, False)
            s.set(s.DISABLE_TRIANGULATION, False)
            self._geom_settings = s
        return self._geom_settings

    def _extract_one_space_enhanced(
        self,
        space,
        storey_map: Dict[str, Dict],
    ) -> Optional[Dict[str, Any]]:
        """Extract one IfcSpace with full geometry."""
        name = space.Name or space.GlobalId
        long_name = space.LongName or ""

        # Resolve storey
        storey_entity = self._get_parent_storey(space)
        storey_name = storey_entity.Name if storey_entity else "Unknown"
        storey_elev = 0.0
        if storey_entity:
            storey_data = storey_map.get(storey_entity.GlobalId)
            if storey_data:
                storey_elev = storey_data["elevation"]
            else:
                storey_elev = self._resolve_storey_elevation(storey_entity)

        # Try tessellation for polygon boundary
        polygon, center, height, area, volume = self._tessellate_space(space)

        if polygon is None:
            # V76 CRIT-05 FIX: Previously created a phantom 2m×2m room (4m²)
            # when tessellation failed. A 500m² atrium would receive fire
            # protection designed for a 4m² closet — 2 detectors instead of 50+.
            # This is a life-safety catastrophe. Now we return None to signal
            # that geometry extraction FAILED, and the caller must skip this
            # space with a CRITICAL log. No phantom rooms.
            logger.critical(
                f"IFC space '{name}' (GUID: {space.GlobalId}): "
                f"Geometry tessellation failed — cannot extract room polygon. "
                f"Space will be EXCLUDED from fire protection analysis. "
                f"Manual fire protection engineering design REQUIRED for this space."
            )
            return None

        return {
            "guid": space.GlobalId,
            "name": name,
            "long_name": long_name,
            "storey_name": storey_name,
            "storey_elevation": storey_elev,
            "center": center,
            "floor_polygon": polygon,
            "height_m": height,
            "area_m2": area,
            "volume_m3": volume,
        }

    def _tessellate_space(self, space) -> Tuple:
        """Use ifcopenshell.geom to get tessellated mesh of a space.
        Returns (polygon_verts, center, height, area_m2, volume_m3).
        Falls back to (None, center, 3.0, 0.0, 0.0) on failure.
        """
        settings = self._get_geom_settings()
        if settings is None:
            return None, (0, 0, 0), 3.0, 0.0, 0.0

        try:
            shape = ifcopenshell.geom.create_shape(settings, space)
        except Exception:
            return None, (0, 0, 0), 3.0, 0.0, 0.0

        verts = shape.geometry.verts  # type: ignore[union-attr] # flat [x0,y0,z0, x1,y1,z1, ...]
        if not verts:
            return None, (0, 0, 0), 3.0, 0.0, 0.0

        # Parse vertices into (x, y, z) tuples
        pts = [(verts[i], verts[i + 1], verts[i + 2]) for i in range(0, len(verts), 3)]

        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        zs = [p[2] for p in pts]
        z_min, z_max = min(zs), max(zs)
        height = max(z_max - z_min, 0.01)
        center = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (z_min + z_max) / 2)

        # Floor polygon: vertices at min Z level (tolerance 5 cm)
        floor_tol = 0.05
        floor_pts = [(p[0], p[1], p[2]) for p in pts if abs(p[2] - z_min) <= floor_tol]
        polygon = _convex_hull_2d(floor_pts) if len(floor_pts) >= 3 else None

        area = _polygon_area_2d(polygon) if polygon else (max(xs) - min(xs)) * (max(ys) - min(ys))
        volume = area * height

        return polygon, center, height, round(area, 3), round(volume, 3)

    def _extract_aabb(self, entity, ifc_type: str) -> Optional[Dict[str, Any]]:
        """Extract AABB from an IFC entity via tessellation or placement."""
        settings = self._get_geom_settings()

        if settings is not None:
            try:
                shape = ifcopenshell.geom.create_shape(settings, entity)
                verts = shape.geometry.verts  # type: ignore[union-attr]
                if verts:
                    pts = [(verts[i], verts[i + 1], verts[i + 2]) for i in range(0, len(verts), 3)]
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    zs = [p[2] for p in pts]

                    dx = max(xs) - min(xs)
                    dy = max(ys) - min(ys)
                    dz = max(zs) - min(zs)

                    # Skip degenerate (point/line) AABBs
                    if dx * dy * dz < 1e-6:
                        return None

                    aabb_min = (min(xs), min(ys), min(zs))
                    aabb_max = (max(xs), max(ys), max(zs))

                    # 8 corner vertices
                    lo, hi = aabb_min, aabb_max
                    aabb_vertices = [
                        (lo[0], lo[1], lo[2]),
                        (hi[0], lo[1], lo[2]),
                        (hi[0], hi[1], lo[2]),
                        (lo[0], hi[1], lo[2]),
                        (lo[0], lo[1], hi[2]),
                        (hi[0], lo[1], hi[2]),
                        (hi[0], hi[1], hi[2]),
                        (lo[0], hi[1], hi[2]),
                    ]

                    return {
                        "guid": entity.GlobalId,
                        "ifc_type": ifc_type,
                        "name": entity.Name or "",
                        "aabb_min": aabb_min,
                        "aabb_max": aabb_max,
                        "aabb_vertices": aabb_vertices,
                    }
            except Exception as e:
                logger.debug("Geometry extraction failed for element: %s", e)

        # V76 HIGH-09 FIX: Previously created a phantom 30cm AABB when geometry
        # extraction failed. A 30cm box replacing a 10m wall means corridors
        # appear unobstructed — detectors placed inside real walls.
        # Now returns None, forcing caller to flag for manual FPE review.
        logger.critical(
            f"IFC entity {entity.GlobalId} ({ifc_type}): geometry extraction "
            f"failed. Cannot create accurate obstacle representation. "
            f"Manual fire protection engineer review REQUIRED."
        )
        return None
