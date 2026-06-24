"""fire_zone_engine.py — NFPA 72 Fire Zone Clustering Engine
=========================================================

Groups rooms into fire alarm zones per NFPA 72 §21.3.3 and
local code requirements. Each zone is a logical grouping of
detectors on the same notification circuit of the FACP.

Consultant #6 Criticism #2 — CONCEPT ACCEPTED, IMPLEMENTATION REJECTED:
  The consultant's FireZoneManager used simple area-based bin packing
  (sort by area, fill zones greedily). This is REJECTED because:

  1. It ignores room adjacency — physically adjacent rooms should
     preferably be in the same zone for logical FACP programming.
  2. It uses a single hard-coded 2000 sqm limit — actual limits
     vary by code (NFPA 72: 250 devices/zone, local codes: area limits).
  3. It doesn't account for different occupancy types needing
     separate zones (e.g., boiler rooms on separate zones).
  4. It doesn't integrate with the panel optimizer or loop designer.

  ACCEPTED: The fire zone concept is a real gap in the current system.
  This implementation uses adjacency-aware clustering with configurable
  constraints.

NFPA 72 References:
  - §21.3.3: Zone requirements
  - §21.2.2: Maximum 250 devices per panel
  - §10.4.4: Zone identification
  - Local codes may impose additional area limits (e.g., 2000 sqm)

Architecture:
  - FireZone: A zone with rooms, total area, detector count, zone ID
  - FireZoneEngine: Clusters rooms into zones respecting constraints
  - Adjacency: Optional — if adjacency info not provided, falls back
    to area-based grouping (same as consultant's approach but with
    proper constraint handling)
  - Integration point: FloorReport can carry zone assignments
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────
# Zone Constraints
# ──────────────────────────────────────────────────────────────────


@dataclass
class ZoneConstraints:
    """Constraints for fire zone grouping.

    NFPA 72 does NOT specify a maximum zone area — it specifies a
    maximum number of devices per zone (implied by §21.2.2 panel limit).
    However, many local codes impose area limits (2000 sqm is common
    in Middle Eastern codes).

    Attributes:
        max_area_sqm: Maximum zone area in square meters.
            2000 sqm is common in GCC codes. 0 = no area limit.
        max_detectors_per_zone: Maximum detectors per zone.
            NFPA 72 §21.2.2 implies ~250 per panel, but zones are
            typically much smaller. Default 100 is conservative.
        max_rooms_per_zone: Maximum rooms per zone. 0 = no limit.
        separate_occupancy_types: If True, rooms with different
            occupancy types go in separate zones (e.g., boiler rooms).
        prefer_adjacent: If True, prefer grouping adjacent rooms.
        max_slc_devices_per_loop: Maximum devices per SLC loop.
            NFPA 72 §21.2.2 limits 250 devices per SLC loop.
            This is a PANEL/LOOP constraint, not a zone constraint.
            Zones are typically much smaller. Included here for
            validation warnings when zone assignments exceed loop capacity.
            (Consultant #7 — concept accepted, threshold corrected: 250 is
            the SLC loop limit, NOT the zone limit. Zone default remains 100.)

    """

    max_area_sqm: float = 1858.0  # NFPA 72 §21.3.4 limit ≈ 20,000 sq ft = 1,858 sqm
    max_detectors_per_zone: int = 100
    max_rooms_per_zone: int = 0  # no limit
    separate_occupancy_types: bool = True
    prefer_adjacent: bool = True
    max_slc_devices_per_loop: int = 250  # NFPA 72 §21.2.2 SLC loop capacity


# ──────────────────────────────────────────────────────────────────
# Fire Zone
# ──────────────────────────────────────────────────────────────────


@dataclass
class FireZone:
    """A fire alarm zone grouping rooms on the same FACP circuit.

    Attributes:
        zone_id: Zone identifier (e.g., "Z-01").
        rooms: List of room IDs in this zone.
        total_area_sqm: Total area of all rooms in the zone.
        total_detectors: Total detector count across all rooms.
        occupancy_types: Set of occupancy types in this zone.
        floor_id: Floor identifier this zone belongs to.
        zone_type: "alarm", "supervisory", or "trouble".

    """

    zone_id: str
    rooms: List[str] = field(default_factory=list)
    total_area_sqm: float = 0.0
    total_detectors: int = 0
    occupancy_types: Set[str] = field(default_factory=set)
    floor_id: str = ""
    zone_type: str = "alarm"


# ──────────────────────────────────────────────────────────────────
# Zone Report
# ──────────────────────────────────────────────────────────────────


@dataclass
class ZoneReport:
    """Report of zone assignments for a floor.

    Attributes:
        floor_id: Floor identifier.
        zones: List of FireZone objects.
        total_zones: Number of zones created.
        total_area_sqm: Total area across all zones.
        total_detectors: Total detectors across all zones.
        warnings: List of advisory warnings.
        unzoned_rooms: Room IDs that couldn't be assigned (overflow).

    """

    floor_id: str
    zones: List[FireZone] = field(default_factory=list)
    total_zones: int = 0
    total_area_sqm: float = 0.0
    total_detectors: int = 0
    warnings: List[str] = field(default_factory=list)
    unzoned_rooms: List[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────
# Fire Zone Engine
# ──────────────────────────────────────────────────────────────────


class FireZoneEngine:
    """NFPA 72 fire zone clustering engine.

    Groups rooms into fire alarm zones respecting constraints on area,
    detector count, and occupancy type separation.

    Strategy:
      1. Group rooms by occupancy type (if separate_occupancy_types)
      2. Within each occupancy group, cluster adjacent rooms together
         (if adjacency info available) or by proximity (centroid distance)
      3. Apply area and detector count constraints to split clusters
      4. Assign sequential zone IDs

    If no adjacency information is provided, falls back to greedy
    area-based grouping (largest rooms first).

    Usage:
        engine = FireZoneEngine()
        report = engine.cluster_floor(
            floor_id="GF",
            rooms=[
                {"id": "R1", "area": 50.0, "detectors": 2, "occupancy": "office"},
                {"id": "R2", "area": 80.0, "detectors": 3, "occupancy": "office"},
            ],
        )
        for zone in report.zones:
            print(f"Zone {zone.zone_id}: {zone.rooms} ({zone.total_area_sqm} sqm)")
    """

    def __init__(self, constraints: Optional[ZoneConstraints] = None):
        self.constraints = constraints or ZoneConstraints()

    def cluster_floor(
        self,
        floor_id: str,
        rooms: List[dict],
        adjacency: Optional[Dict[str, Set[str]]] = None,
    ) -> ZoneReport:
        """Cluster rooms into fire zones for a single floor.

        Args:
            floor_id: Floor identifier.
            rooms: List of room dicts. Each must have:
                - id (str): Room identifier
                - area (float): Room area in sqm
                - detectors (int): Number of detectors in room
                Optional:
                - occupancy (str): Occupancy type
                - centroid (Tuple[float,float]): Room centroid for proximity
            adjacency: Optional adjacency map. {room_id: set of adjacent room_ids}.
                If provided, adjacent rooms are preferentially grouped together.
                If None, falls back to area-based grouping.

        Returns:
            ZoneReport with zone assignments.

        """
        report = ZoneReport(floor_id=floor_id)

        if not rooms:
            report.warnings.append("No rooms provided for zone clustering.")
            return report

        # Normalize room dicts
        normalized = []
        for r in rooms:
            room_id = r.get("id", r.get("room_id", ""))
            area = r.get("area", 0.0)
            detectors = r.get("detectors", r.get("detector_count", 0))
            occupancy = r.get("occupancy", r.get("room_type", "standard"))
            centroid = r.get("centroid", None)
            normalized.append(
                {
                    "id": room_id,
                    "area": float(area),
                    "detectors": int(detectors),
                    "occupancy": str(occupancy).lower(),
                    "centroid": centroid,
                }
            )

        # Step 1: Group by occupancy type (if required)
        if self.constraints.separate_occupancy_types:
            occupancy_groups: Dict[str, List[dict]] = {}
            for r in normalized:
                occ = r["occupancy"]
                if occ not in occupancy_groups:
                    occupancy_groups[occ] = []
                occupancy_groups[occ].append(r)
        else:
            occupancy_groups = {"_all": normalized}

        # Step 2: Create zones within each occupancy group
        zone_counter = 0
        for _occ_type, occ_rooms in occupancy_groups.items():
            if self.constraints.prefer_adjacent and adjacency:
                # Adjacency-aware clustering
                clusters = self._cluster_adjacent(occ_rooms, adjacency)
            else:
                # Fallback: area-based grouping (largest first)
                clusters = self._cluster_by_area(occ_rooms)

            # Step 3: Apply constraints to each cluster (split if needed)
            for cluster in clusters:
                split_zones = self._apply_constraints(cluster, zone_counter, floor_id)
                for z in split_zones:
                    report.zones.append(z)
                    zone_counter += 1

        # Populate report
        report.total_zones = len(report.zones)
        report.total_area_sqm = sum(z.total_area_sqm for z in report.zones)
        report.total_detectors = sum(z.total_detectors for z in report.zones)

        # Check for unzoned rooms
        zoned_room_ids = set()
        for z in report.zones:
            zoned_room_ids.update(z.rooms)
        all_room_ids = {r["id"] for r in normalized}
        report.unzoned_rooms = list(all_room_ids - zoned_room_ids)

        if report.unzoned_rooms:
            report.warnings.append(
                f"UNZONED rooms (could not assign): {report.unzoned_rooms}. Review manually for zone assignment."
            )

        # Validate constraints
        for z in report.zones:
            if self.constraints.max_area_sqm > 0 and z.total_area_sqm > self.constraints.max_area_sqm:
                report.warnings.append(
                    f"Zone {z.zone_id} area {z.total_area_sqm:.0f} sqm exceeds "
                    f"limit {self.constraints.max_area_sqm} sqm. "
                    f"Review with AHJ for exception or split."
                )
            if z.total_detectors > self.constraints.max_detectors_per_zone:
                report.warnings.append(
                    f"Zone {z.zone_id} has {z.total_detectors} detectors > "
                    f"limit {self.constraints.max_detectors_per_zone}. "
                    f"Split zone or add panel."
                )

        # Per-floor detector count review (Consultant #7 — NFPA 72 §21.2.2)
        # This validates the floor-level count only; loop-level validation
        # (aggregating across floors sharing a loop) must be done at building scope.
        if report.total_detectors > self.constraints.max_slc_devices_per_loop:
            report.warnings.append(
                f"FLOOR_DETECTOR_COUNT_REVIEW: Floor has {report.total_detectors} total detectors, "
                f"exceeding SLC loop capacity of {self.constraints.max_slc_devices_per_loop} "
                f"devices per NFPA 72 §21.2.2. "
                f"This is a per-floor count; loop-level validation is required at building scope."
            )

        logger.info(
            "FireZoneEngine: floor=%s zones=%d rooms=%d detectors=%d",
            floor_id,
            report.total_zones,
            len(normalized),
            report.total_detectors,
        )

        return report

    def _cluster_adjacent(
        self,
        rooms: List[dict],
        adjacency: Dict[str, Set[str]],
    ) -> List[List[dict]]:
        """Cluster rooms using adjacency information (BFS-based).

        Groups connected rooms (sharing walls/corridors) together,
        then splits if area/detector constraints exceeded.

        Args:
            rooms: List of room dicts with 'id', 'area', 'detectors'.
            adjacency: {room_id: set of adjacent room_ids}.

        Returns:
            List of clusters (each cluster is a list of room dicts).

        """
        room_map = {r["id"]: r for r in rooms}
        visited: Set[str] = set()
        clusters: List[List[dict]] = []

        for room in rooms:
            room_id = room["id"]
            if room_id in visited:
                continue

            # BFS from this room
            cluster: List[dict] = []
            queue = [room_id]
            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                if current not in room_map:
                    continue
                visited.add(current)
                cluster.append(room_map[current])
                # Add adjacent rooms to queue
                for neighbor in adjacency.get(current, set()):
                    if neighbor not in visited and neighbor in room_map:
                        queue.append(neighbor)

            if cluster:
                clusters.append(cluster)

        return clusters

    def _cluster_by_area(self, rooms: List[dict]) -> List[List[dict]]:
        """Fallback: group rooms by area (largest first).

        This is the consultant's approach (greedy bin packing).
        Used when no adjacency info is available.

        Args:
            rooms: List of room dicts with 'area'.

        Returns:
            List of clusters (each a list of room dicts).

        """
        sorted_rooms = sorted(rooms, key=lambda r: r["area"], reverse=True)
        # Put all rooms in one cluster; constraints will split later
        return [sorted_rooms]

    def _apply_constraints(
        self,
        cluster: List[dict],
        zone_counter: int,
        floor_id: str = "",
    ) -> List[FireZone]:
        """Split a cluster into zones respecting constraints.

        Args:
            cluster: List of room dicts.
            zone_counter: Starting zone counter for ID generation.
            floor_id: Floor identifier for zone ID prefix and FireZone.floor_id.

        Returns:
            List of FireZone objects.

        """
        max_area = self.constraints.max_area_sqm
        max_det = self.constraints.max_detectors_per_zone
        max_rooms = self.constraints.max_rooms_per_zone

        zones: List[FireZone] = []
        _zid = f"{floor_id}-Z{zone_counter + 1:02d}" if floor_id else f"Z-{zone_counter + 1:03d}"
        current = FireZone(
            zone_id=_zid,
            floor_id=floor_id,
        )
        occupancy_types: Set[str] = set()

        for room in cluster:
            room_area = room["area"]
            room_det = room["detectors"]
            room_occ = room["occupancy"]

            # Check if adding this room would exceed constraints
            area_ok = max_area <= 0 or current.total_area_sqm + room_area <= max_area
            det_ok = max_det <= 0 or current.total_detectors + room_det <= max_det
            rooms_ok = max_rooms <= 0 or len(current.rooms) < max_rooms

            if not area_ok or not det_ok or not rooms_ok:
                # Close current zone and start a new one
                if current.rooms:
                    current.occupancy_types = occupancy_types.copy()
                    zones.append(current)
                zone_counter += 1
                _zid = f"{floor_id}-Z{zone_counter + 1:02d}" if floor_id else f"Z-{zone_counter + 1:03d}"
                current = FireZone(
                    zone_id=_zid,
                    floor_id=floor_id,
                )
                occupancy_types.clear()

            # Add room to current zone
            current.rooms.append(room["id"])
            current.total_area_sqm += room_area
            current.total_detectors += room_det
            occupancy_types.add(room_occ)

        # Don't forget the last zone
        if current.rooms:
            current.occupancy_types = occupancy_types.copy()
            zones.append(current)

        return zones

    def build_zone_map(self, report: ZoneReport) -> Dict[str, str]:
        """Build a zone_map dict from a ZoneReport for fault isolator injection.

        The returned dict maps room_id -> zone_id, suitable for passing to
        :func:`fireai.core.fault_isolator_injector.inject_fault_isolators`
        as the ``zone_map`` parameter.

        This is the integration bridge between the fire zone engine and the
        fault isolator injector — without it, the injector cannot determine
        zone boundaries and may place isolators at wrong positions.

        NFPA 72 §12.3.2 requires a single fault to affect only one zone,
        so correct zone boundary identification is critical.

        Args:
            report: ZoneReport from :meth:`cluster_floor`.

        Returns:
            Dict mapping room_id -> zone_id (both strings).

        """
        zone_map: Dict[str, str] = {}
        for zone in report.zones:
            for room_id in zone.rooms:
                zone_map[room_id] = zone.zone_id
        return zone_map
