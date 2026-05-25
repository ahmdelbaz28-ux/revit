"""
validation/spatial_field_engine.py — SpatialFieldEngine (Vectorised)
=====================================================================
B6 FIX: evaluate_compliance() was O(grid × devices × obstructions).
New:    Vectorised NumPy distance matrix + STRtree LOS for hits only.

Same pattern as truth_deriver.py B2 fix — applied here.

V30 NOTE:
  This is a NEW vectorised implementation in the validation/ layer,
  separate from the deprecated root-level spatial_field_engine.py.
  The root-level file is retained for backward compatibility.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
    _NP = True
except ImportError:
    _NP = False

try:
    from shapely.geometry import LineString
    from shapely.strtree import STRtree
    _SHAPELY = True
except ImportError:
    _SHAPELY = False


@dataclass
class ComplianceResult:
    """Spatial field compliance result."""
    room_id:        str
    coverage_pct:   float
    violation_pts:  List[Tuple[float, float]] = field(default_factory=list)
    wall_violations: int = 0
    nfpa_compliant: bool = True
    method:         str  = "vectorised"


class SpatialFieldEngine:
    """
    B6 FIX: Vectorised spatial field compliance evaluation.

    evaluate_compliance() was O(G × D × O) Shapely calls.
    Now: O(G) NumPy broadcast + O(hits × O) STRtree LOS.
    """

    def __init__(
        self,
        grid_spacing:    float = 0.25,
        detector_radius: float = 6.37,
        wall_min:        float = 0.10,
    ) -> None:
        self.grid_spacing    = grid_spacing
        self.detector_radius = detector_radius
        self.wall_min        = wall_min

    def evaluate_compliance(
        self,
        room_polygon:      Any,   # Shapely Polygon
        device_positions:  List[Tuple[float, float]],
        obstructions:      List[Any] = None,
        room_id:           str  = "room",
    ) -> ComplianceResult:
        """
        B6 FIX: Vectorised grid compliance.

        1. Generate interior grid (Shapely batch contains).
        2. NumPy broadcast: all-pairs grid×device distance in one op.
        3. Points within radius → candidate covered.
        4. Only in-radius points checked with Shapely STRtree LOS.
        """
        obstructions = obstructions or []
        if room_polygon is None:
            return ComplianceResult(room_id=room_id, coverage_pct=0.0,
                                    nfpa_compliant=False)

        # Generate grid
        bounds   = room_polygon.bounds
        min_x, min_y, max_x, max_y = bounds
        grid_pts: List[Tuple[float, float]] = []
        x = min_x + self.grid_spacing / 2
        while x < max_x:
            y = min_y + self.grid_spacing / 2
            while y < max_y:
                grid_pts.append((x, y))
                y += self.grid_spacing
            x += self.grid_spacing

        if not grid_pts:
            return ComplianceResult(room_id=room_id, coverage_pct=100.0,
                                    nfpa_compliant=True)

        if _SHAPELY:
            import shapely
            pts_geom = shapely.points(grid_pts)
            mask     = shapely.contains_properly(room_polygon, pts_geom)
            grid_pts = [grid_pts[i] for i in range(len(grid_pts)) if mask[i]]

        total_pts = len(grid_pts)
        if total_pts == 0:
            return ComplianceResult(room_id=room_id, coverage_pct=100.0)

        if not device_positions:
            return ComplianceResult(
                room_id=room_id, coverage_pct=0.0,
                violation_pts=grid_pts, nfpa_compliant=False)

        # STRtree for obstructions
        obs_tree = None
        obs_geoms = []
        if _SHAPELY and obstructions:
            obs_geoms = [getattr(o, "shapely_geom",
                         getattr(o, "geometry", None)) for o in obstructions]
            valid = [g for g in obs_geoms if g is not None]
            if valid:
                obs_tree = STRtree(valid)

        R2 = self.detector_radius ** 2
        covered = 0
        violations: List[Tuple[float, float]] = []

        if _NP and len(grid_pts) > 20:
            gp   = np.array(grid_pts,       dtype=np.float64)
            dp   = np.array(device_positions, dtype=np.float64)
            diff  = gp[:, np.newaxis, :] - dp[np.newaxis, :, :]
            dist2 = (diff * diff).sum(axis=2)
            min_d2   = dist2.min(axis=1)
            best_det = dist2.argmin(axis=1)

            for i in range(total_pts):
                gx, gy = grid_pts[i]
                if min_d2[i] > R2:
                    violations.append((gx, gy))
                    continue
                if obs_tree is None:
                    covered += 1
                    continue
                # LOS check
                dx, dy = device_positions[int(best_det[i])]
                los = LineString([(gx, gy), (dx, dy)])
                blocked = any(
                    obs_geoms[idx] is not None
                    and los.intersects(obs_geoms[idx])
                    for idx in obs_tree.query(los)
                )
                if not blocked:
                    covered += 1
                else:
                    # Try other devices
                    found = False
                    for j, (dx2, dy2) in enumerate(device_positions):
                        if j == int(best_det[i]):
                            continue
                        if dist2[i, j] <= R2:
                            los2 = LineString([(gx, gy), (dx2, dy2)])
                            b2 = any(
                                obs_geoms[k] is not None
                                and los2.intersects(obs_geoms[k])
                                for k in obs_tree.query(los2)
                            )
                            if not b2:
                                found = True
                                break
                    if found:
                        covered += 1
                    else:
                        violations.append((gx, gy))
        else:
            for gx, gy in grid_pts:
                pt_covered = False
                for dx, dy in device_positions:
                    ddx = gx - dx
                    ddy = gy - dy
                    if ddx*ddx + ddy*ddy > R2:
                        continue
                    if obs_tree is None:
                        pt_covered = True
                        break
                    los = LineString([(gx, gy), (dx, dy)])
                    if not any(
                        obs_geoms[k] is not None
                        and los.intersects(obs_geoms[k])
                        for k in obs_tree.query(los)
                    ):
                        pt_covered = True
                        break
                if pt_covered:
                    covered += 1
                else:
                    violations.append((gx, gy))

        coverage_pct = 100.0 * covered / total_pts
        compliant    = coverage_pct >= 100.0 and len(violations) == 0

        return ComplianceResult(
            room_id=room_id,
            coverage_pct=round(coverage_pct, 4),
            violation_pts=violations,
            nfpa_compliant=compliant,
            method="vectorised_numpy",
        )

    def evaluate_batch(
        self,
        rooms_data: List[Tuple[Any, List[Tuple[float,float]], str]],
    ) -> List[ComplianceResult]:
        """Batch evaluate N rooms. Each independent — parallelisable."""
        return [
            self.evaluate_compliance(poly, dets, room_id=rid)
            for poly, dets, rid in rooms_data
        ]
