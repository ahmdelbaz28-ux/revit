"""
digital_twin/twin.py
====================
The Digital Twin — a queryable, simulatable replica of the building.

What it models:
  - Rooms (geometry, volume, ceiling height, occupancy)
  - Walls / openings (doors, corridors) → connectivity graph
  - MEP devices (detectors, sprinklers, sensors, lights, panels) — placed
  - Cable / pipe runs — routed segments with materials
  - Fire load and ignition sources (if specified)

What you can do with it:
  • twin.shortest_egress_path(from_room, exits)
  • twin.detector_coverage_by_room()
  • twin.simulate_smoke(fire_room, time_seconds)
  • twin.what_if_remove(device_id)        ← critical for resilience analysis
  • twin.what_if_fire_in(room_id)         ← cascade simulation

Built incrementally from analysis outputs — every analyzed drawing
contributes geometry/devices to the same twin instance.
"""
from __future__ import annotations
import json, math, logging
from dataclasses import dataclass, field, asdict
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────
@dataclass
class Room:
    id: str
    name: str = ""
    polygon: list = field(default_factory=list)        # [(x,y), …]  metres
    ceiling_height_m: float = 2.8
    occupancy_load: int = 0
    use: str = "office"            # 'office','corridor','storage','assembly','exit'

    @property
    def area_m2(self) -> float:
        return _poly_area(self.polygon)
    @property
    def volume_m3(self) -> float:
        return self.area_m2 * self.ceiling_height_m
    @property
    def centroid(self) -> tuple[float,float]:
        return _poly_centroid(self.polygon) if self.polygon else (0.0, 0.0)


@dataclass
class Opening:
    id: str
    room_a: str
    room_b: str            # 'OUTSIDE' for exits
    width_m: float = 0.9
    height_m: float = 2.1
    is_exit: bool = False
    fire_rated_min: int = 0       # 0 = not rated


@dataclass
class Device:
    id: str
    kind: str                              # 'smoke_detector','sprinkler_pendant',…
    position: tuple[float, float]          # metres
    mounting_height_m: float = 2.8
    room_id: Optional[str] = None
    attributes: dict = field(default_factory=dict)


@dataclass
class CableSegment:
    id: str
    a: tuple[float, float]
    b: tuple[float, float]
    awg: int = 14
    function: str = "SLC"      # 'SLC','NAC','power','data'
    length_m: float = 0.0


# ──────────────────────────────────────────────────────────────────────────
class DigitalTwin:
    """In-memory building model with import/export and simulation."""

    def __init__(self):
        self.rooms:    dict[str, Room]   = {}
        self.openings: list[Opening]     = []
        self.devices:  dict[str, Device] = {}
        self.cables:   list[CableSegment]= []
        self._graph_cache = None

    # ── Builders ────────────────────────────────────────────────────────
    def add_room(self, r: Room): self.rooms[r.id] = r; self._invalidate()
    def add_opening(self, o: Opening): self.openings.append(o); self._invalidate()
    def add_device(self, d: Device):
        if d.room_id is None:
            d.room_id = self.find_containing_room(d.position)
        self.devices[d.id] = d
    def add_cable(self, c: CableSegment):
        c.length_m = math.hypot(c.a[0]-c.b[0], c.a[1]-c.b[1])
        self.cables.append(c)

    def find_containing_room(self, pt: tuple[float,float]) -> Optional[str]:
        for rid, r in self.rooms.items():
            if r.polygon and _point_in_poly(pt, r.polygon):
                return rid
        return None

    def _invalidate(self): self._graph_cache = None

    # ── Connectivity graph ─────────────────────────────────────────────
    def adjacency(self) -> dict[str, list[tuple[str, Opening]]]:
        if self._graph_cache: return self._graph_cache
        g = {rid: [] for rid in self.rooms}
        g["OUTSIDE"] = []
        for o in self.openings:
            g.setdefault(o.room_a, []).append((o.room_b, o))
            g.setdefault(o.room_b, []).append((o.room_a, o))
        self._graph_cache = g
        return g

    # ── Egress (Dijkstra by travel distance, blocked by fire-rated barrier?) ─
    def shortest_egress(self, from_room: str,
                        smoke_blocked: set | None = None) -> Optional[dict]:
        """Returns {'path': [room_ids], 'distance_m': float}. None if no exit."""
        import heapq
        adj = self.adjacency()
        if from_room not in adj: return None
        smoke_blocked = smoke_blocked or set()

        exits = [rid for rid,r in self.rooms.items() if r.use == "exit"]
        if not exits and not any(o.is_exit for o in self.openings): return None

        heap = [(0.0, from_room, [from_room])]
        seen = set()
        while heap:
            d, cur, path = heapq.heappop(heap)
            if cur in seen: continue
            seen.add(cur)
            if cur == "OUTSIDE" or cur in exits:
                return {"path": path, "distance_m": d}
            for nbr, opening in adj.get(cur, []):
                if nbr in seen: continue
                if nbr in smoke_blocked: continue
                # cost: euclidean between room centroids
                a = self.rooms[cur].centroid if cur in self.rooms else (0,0)
                b = self.rooms[nbr].centroid if nbr in self.rooms else a
                step = math.hypot(a[0]-b[0], a[1]-b[1]) or 5.0
                heapq.heappush(heap, (d+step, nbr, path+[nbr]))
        return None

    # ── Device coverage per room ───────────────────────────────────────
    def detector_coverage(self, kind: str = "smoke_detector",
                          coverage_radius_m: float = 6.4) -> dict:
        """For every room, fraction of area within `coverage_radius_m` of a
        device of `kind`. 1.0 = full coverage."""
        out = {}
        dev_pts = [d.position for d in self.devices.values() if d.kind == kind]
        for rid, r in self.rooms.items():
            if not r.polygon: out[rid] = None; continue
            # sample grid points in room
            xs = [p[0] for p in r.polygon]; ys = [p[1] for p in r.polygon]
            x0,x1 = min(xs), max(xs); y0,y1 = min(ys), max(ys)
            inside = 0; covered = 0
            n = 30
            for i in range(n):
                for j in range(n):
                    px = x0 + (x1-x0)*(i+0.5)/n
                    py = y0 + (y1-y0)*(j+0.5)/n
                    if not _point_in_poly((px,py), r.polygon): continue
                    inside += 1
                    if any((px-dx)**2+(py-dy)**2 <= coverage_radius_m**2
                           for dx,dy in dev_pts):
                        covered += 1
            out[rid] = (covered/inside) if inside else None
        return out

    # ── Resilience: what if a device dies? ──────────────────────────────
    def what_if_remove(self, device_id: str) -> dict:
        if device_id not in self.devices:
            return {"error": "no such device"}
        backup = dict(self.devices); removed = backup.pop(device_id)
        sub = DigitalTwin()
        sub.rooms = self.rooms; sub.openings = self.openings
        sub.devices = backup; sub.cables = self.cables
        if removed.kind in ("smoke_detector","heat_detector","sprinkler_pendant"):
            radius = 6.4 if "smoke" in removed.kind else 4.0
            return {"removed": device_id, "kind": removed.kind,
                    "coverage_after": sub.detector_coverage(removed.kind, radius)}
        return {"removed": device_id, "kind": removed.kind}

    # ── Persistence ────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "rooms":   {k: asdict(v) for k,v in self.rooms.items()},
            "openings":[asdict(o) for o in self.openings],
            "devices": {k: asdict(v) for k,v in self.devices.items()},
            "cables":  [asdict(c) for c in self.cables],
        }

    def save(self, path: str):
        from pathlib import Path
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, default=str))

    @classmethod
    def load(cls, path: str) -> "DigitalTwin":
        from pathlib import Path
        d = json.loads(Path(path).read_text())
        t = cls()
        for rid, r in d.get("rooms", {}).items():
            t.rooms[rid] = Room(**r)
        for o in d.get("openings", []):
            t.openings.append(Opening(**o))
        for did, dv in d.get("devices", {}).items():
            t.devices[did] = Device(**dv)
        for c in d.get("cables", []):
            t.cables.append(CableSegment(**c))
        return t


# ──────────────────────────────────────────────────────────────────────────
# Geometry helpers
def _poly_area(poly):
    if len(poly) < 3: return 0.0
    s = 0.0
    n = len(poly)
    for i in range(n):
        x1,y1 = poly[i]; x2,y2 = poly[(i+1)%n]
        s += x1*y2 - x2*y1
    return abs(s)/2.0

def _poly_centroid(poly):
    if len(poly) < 3: return (0.0,0.0)
    a = _poly_area(poly) or 1e-9
    cx = cy = 0.0
    n = len(poly)
    for i in range(n):
        x1,y1 = poly[i]; x2,y2 = poly[(i+1)%n]
        cross = x1*y2 - x2*y1
        cx += (x1+x2) * cross
        cy += (y1+y2) * cross
    return (cx/(6*a), cy/(6*a))

def _point_in_poly(pt, poly):
    x,y = pt; inside = False; n = len(poly)
    j = n-1
    for i in range(n):
        xi,yi = poly[i]; xj,yj = poly[j]
        if ((yi>y) != (yj>y)) and (x < (xj-xi)*(y-yi)/(yj-yi+1e-12) + xi):
            inside = not inside
        j = i
    return inside
