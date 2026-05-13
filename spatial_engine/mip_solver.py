"""
OptimalMIPEngine - Mixed Integer Programming Solver
FireAI V5 - NFPA 72 Compliant Device Placement
================================================
CRITICAL SAFETY SYSTEM: Any modification requires peer review.
"""

from typing import List, Tuple, Dict, Optional
from pulp import LpProblem, LpMinimize, LpVariable, LpBinary, lpSum, LpStatus, value
import math
from shapely.geometry import Point, Polygon

from nfpa72_models import (
    RoomSpec, DetectorType, CoverageGeometry, CeilingType, NFPAComplianceError,
    CeilingSpec as CeilingSpecModel, HeatDetectorSpec as HeatDetectorSpecModel
)
from nfpa72_calculations import get_smoke_detector_radius, get_heat_detector_placement_params
from nfpa72_coverage import get_sloped_ceiling_constraints, verify_full_coverage


class OptimalMIPEngine:
    """
    MIP Solver for NFPA 72 V5 compliant placements.
    CRITICAL: Accepts RoomSpec ONLY. Legacy grid_size/radius REMOVED.
    Supports BOTH old format (name/width/depth/height) AND new format.
    """

    def __init__(self, room_spec):
        """
        Initialize with RoomSpec object.
        
        Args:
            room_spec: RoomSpec object with room details
            
        Raises:
            TypeError: If room_spec is not a RoomSpec object
        """
        # Support both old and new RoomSpec formats
        if hasattr(room_spec, 'room_id'):
            # New format - already has polygon and ceiling_spec
            self.room_spec = room_spec
            self.polygon = room_spec.polygon
            self.ceiling = room_spec.ceiling_spec
            self.detector_type = getattr(room_spec, 'detector_type', DetectorType.SMOKE)
        elif hasattr(room_spec, 'name') and hasattr(room_spec, 'width_m'):
            # Old format - build polygon and ceiling_spec from dimensions
            self.room_spec = room_spec
            # Build polygon from dimensions
            if hasattr(room_spec, 'polygon') and room_spec.polygon is not None:
                self.polygon = room_spec.polygon
            else:
                self.polygon = ShapelyPolygon([
                    (0, 0),
                    (room_spec.width_m, 0),
                    (room_spec.width_m, room_spec.depth_m),
                    (0, room_spec.depth_m)
                ])
            # Build ceiling_spec from height
            if hasattr(room_spec, 'ceiling_spec') and room_spec.ceiling_spec is not None:
                self.ceiling = room_spec.ceiling_spec
            else:
                self.ceiling = CeilingSpec(CeilingType.FLAT, room_spec.height_m, room_spec.height_m, 0.0)
            self.detector_type = getattr(room_spec, 'detector_type', DetectorType.SMOKE)
        else:
            raise TypeError(
                "CRITICAL SAFETY ERROR: OptimalMIPEngine requires RoomSpec object. "
                "Legacy grid_size/radius mode has been REMOVED. "
                "Pass RoomSpec(name='room', width_m=10, depth_m=10, height_m=3)"
            )

        # Get detector spacing/radius based on ceiling height
        if self.detector_type == DetectorType.SMOKE:
            self.coverage_geo = CoverageGeometry.CIRCULAR
            self.radius = get_smoke_detector_radius(self.ceiling.height_at_low_point_m)
            self.spacing = None
        elif self.detector_type in (DetectorType.HEAT_FIXED_TEMP, DetectorType.HEAT_RATE_OF_RISE, 
                                  DetectorType.HEAT_COMBINATION, DetectorType.SMOKE_HEAT_COMBINATION):
            # Heat detectors use fixed spacing (9.1m = 30ft)
            self.coverage_geo = CoverageGeometry.SQUARE_GRID
            self.spacing = 9.1
            self.radius = self.spacing / 2
        else:
            # Default to smoke
            self.coverage_geo = CoverageGeometry.CIRCULAR
            self.radius = get_smoke_detector_radius(self.ceiling.height_at_low_point_m)
            self.spacing = None

        self.candidates: List[Tuple[float, float]] = []
        self._build_candidates(step_m=0.25)  # Higher resolution for better placement

        self.ridge_zone: Optional[ShapelyPolygon] = None
        self.ridge_indices: List[int] = []
        self._setup_ridge_zone()

    def _setup_coverage_params(self):
        """Set coverage geometry, radius, and spacing based on NFPA 72."""
        if self.detector_type == DetectorType.SMOKE:
            self.coverage_geo = CoverageGeometry.CIRCULAR
            self.radius = get_smoke_detector_radius(self.ceiling.height_at_low_point_m)
            self.spacing = None

        elif self.detector_type in (
            DetectorType.HEAT_FIXED_TEMP,
            DetectorType.HEAT_RATE_OF_RISE,
            DetectorType.HEAT_COMBINATION,
            DetectorType.SMOKE_HEAT_COMBINATION,
        ):
            if self.room_spec.heat_detector_spec is None:
                raise NFPAComplianceError(
                    "HeatDetectorSpec is REQUIRED for heat detectors. "
                    "Provide manufacturer, model_number, and listed_spacing."
                )
            params = get_heat_detector_placement_params(
                spec=self.room_spec.heat_detector_spec,
                ceiling_height_m=self.ceiling.height_at_low_point_m,
                beam_depth_m=0.0,
                ceiling_slope_degrees=self.ceiling.slope_degrees,
            )
            self.coverage_geo = CoverageGeometry.SQUARE_GRID
            self.spacing = params["max_detector_spacing_m"]
            self.radius = self.spacing / 2
        else:
            raise NFPAComplianceError(f"Unsupported detector type: {self.detector_type}")

    def _build_candidates(self, step_m: float = 0.5):
        """
        Generate candidate positions strictly INSIDE the room polygon.
        CRITICAL: Uses polygon.contains() — NEVER bounding box.
        """
        minx, miny, maxx, maxy = self.polygon.bounds
        x = minx
        while x <= maxx:
            y = miny
            while y <= maxy:
                p = Point(x, y)
                if self.polygon.contains(p):
                    self.candidates.append((round(x, 4), round(y, 4)))
                y += step_m
            x += step_m

        if not self.candidates:
            raise NFPAComplianceError(
                f"No candidate positions inside polygon. "
                f"Room area={self.polygon.area:.2f}m². Check geometry validity."
            )

    def _setup_ridge_zone(self):
        """Set up ridge zone constraint for sloped ceilings."""
        if not self.ceiling.is_sloped:
            return

        if self.detector_type != DetectorType.SMOKE:
            return

        constraints = get_sloped_ceiling_constraints(
            self.polygon, self.ceiling, self.detector_type
        )
        if constraints["requires_ridge_row"] and constraints["ridge_zone_polygon"]:
            self.ridge_zone = constraints["ridge_zone_polygon"]
            self.ridge_indices = [
                i for i, (cx, cy) in enumerate(self.candidates)
                if self.ridge_zone.contains(Point(cx, cy))
            ]
            if not self.ridge_indices:
                raise NFPAComplianceError(
                    "Sloped ceiling requires ridge row but no candidate positions "
                    "fall within ridge zone. Increase grid resolution or check geometry."
                )

    def _covers(self, test_point: Tuple[float, float], candidate: Tuple[float, float]) -> bool:
        tx, ty = test_point
        cx, cy = candidate

        if self.coverage_geo == CoverageGeometry.CIRCULAR:
            return math.sqrt((tx - cx) ** 2 + (ty - cy) ** 2) <= self.radius

        elif self.coverage_geo == CoverageGeometry.SQUARE_GRID:
            half = self.spacing / 2
            return abs(tx - cx) <= half and abs(ty - cy) <= half

        return False

    def _build_coverage_pairs(self) -> Dict[int, List[int]]:
        coverage = {}
        for ti, tp in enumerate(self.candidates):
            coverage[ti] = [
                ci for ci, cp in enumerate(self.candidates)
                if self._covers(tp, cp)
            ]
        return coverage

    def solve(self) -> Tuple[List[Tuple[float, float]], int, bool, Dict]:
        coverage = self._build_coverage_pairs()

        uncovered = [ti for ti, cov in coverage.items() if not cov]
        if uncovered:
            raise NFPAComplianceError(
                f"{len(uncovered)} candidate points have zero coverage. "
                f"Radius={self.radius}m may be too small for room geometry."
            )

        prob = LpProblem("FireAI_V5_Placement", LpMinimize)

        x = {
            i: LpVariable(f"x_{i}", cat=LpBinary)
            for i in range(len(self.candidates))
        }

        prob += lpSum(x.values()), "MinimizeDetectors"

        for ti, cov_list in coverage.items():
            prob += lpSum(x[ci] for ci in cov_list) >= 1, f"Coverage_{ti}"
        if self.ridge_indices:
            prob += (
                lpSum(x[i] for i in self.ridge_indices) >= 1,
                "RidgeRow_Minimum"
            )

        # Base Safety Rule: Minimum detectors based on room area
        area = self.polygon.area
        min_detectors = 0
        if area >= 60.0:
            min_detectors = 1  # At least 1 for any viable room
        if area >= 120.0:
            min_detectors = 2  # Minimum for larger rooms
        if min_detectors > 0:
            prob += lpSum(x.values()) >= min_detectors, "Minimum_Safety_Count"

        prob.solve()

        if LpStatus[prob.status] != "Optimal":
            return [], 0, False, {"status": LpStatus[prob.status]}

        selected = [
            self.candidates[i]
            for i, var in x.items()
            if value(var) > 0.5
        ]

        metadata = {
            "status": "Optimal",
            "coverage_geometry": self.coverage_geo.value,
            "detector_type": self.detector_type.value,
            "radius_m": self.radius,
            "spacing_m": self.spacing,
            "candidate_count": len(self.candidates),
            "ridge_zone_required": bool(self.ridge_indices),
        }

        return selected, len(selected), True, metadata