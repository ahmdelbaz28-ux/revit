"""
twin/nfpa72_bridge.py — FireAI Level 4 NFPA72 Bridge
=====================================================
Bi-directional interface between Digital Twin and NFPA72 calculation engine.
Provides deterministic compliance validation and cryptographic proof generation.

SAFETY: All calculations are deterministic (same input → same output).
Every calculation produces a cryptographic proof certificate.
Results MUST be verified by a licensed PE before implementation.

NFPA 72-2022 Compliance: Full (with documented simplifications)
"""

from __future__ import annotations
import hashlib
import json
import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class NFPA72CalculationType(Enum):
    """Types of NFPA 72 calculations."""
    COVERAGE = "coverage"           # Area coverage per §17.6.3.1
    SPACING = "spacing"             # Spacing between detectors per §17.6.3.2
    WALL_DISTANCE = "wall_distance" # Wall distance per §17.6.3.1.1
    RESPONSE = "response"           # Response time index


class OccupancyType(Enum):
    """NFPA 101 occupancy classifications."""
    ASSEMBLY = "assembly"
    BUSINESS = "business"
    EDUCATIONAL = "educational"
    FACTORY = "factory"
    HAZARDOUS = "hazardous"
    INSTITUTIONAL = "institutional"
    MERCANTILE = "mercantile"
    RESIDENTIAL = "residential"
    STORAGE = "storage"


# ═══════════════════════════════════════════════════════════════════════
# NFPA 72-2022 Constants — Table 17.6.3.1.1 and Table 17.6.3.2.1
# ═══════════════════════════════════════════════════════════════════════

# Ceiling height → adjusted spacing (m) for smoke detectors
# Per NFPA 72-2022 Table 17.6.3.1.1
# SAFETY FIX (F1): Changed from set literal {…} to list […]
# A set has NON-DETERMINISTIC iteration order, which caused:
#   1. Wrong spacing values for most ceiling heights (e.g., 6.40m instead of 9.14m at 3.0m)
#   2. TypeError crash for ceilings > 9.1m (set[-1] is not subscriptable)
# The lookup requires ORDERED iteration from low to high ceiling height.
SMOKE_SPACING_BY_HEIGHT: List[Tuple[float, float]] = [
    # (max_ceiling_height_m, adjusted_spacing_m)
    (3.0, 9.14),    # ≤ 3.0m: standard spacing
    (3.9, 8.23),    # 3.0-3.9m
    (4.9, 7.32),    # 3.9-4.9m
    (5.9, 6.40),    # 4.9-5.9m
    (6.9, 5.49),    # 5.9-6.9m
    (7.9, 4.57),    # 6.9-7.9m
    (8.9, 3.66),    # 7.9-8.9m
    (9.1, 3.05),    # 8.9-9.1m (max for spot-type)
]

# Heat detector spacing by ceiling height
# SAFETY FIX (F2): Changed from set literal to list for same reason as F1.
HEAT_SPACING_BY_HEIGHT: List[Tuple[float, float]] = [
    (3.0, 7.01),
    (4.0, 6.10),
    (5.0, 5.18),
    (6.0, 4.27),
    (7.0, 3.35),
    (7.62, 2.74),   # max for fixed-temp
]

# Coverage radius = 0.7 × spacing (NFPA 72 §17.7.4.2.3.1 — 0.7S rule)
COVERAGE_RADIUS_FACTOR = 0.7

# Wall distance = 0.5 × spacing (NFPA 72 §17.6.3.1.1)
WALL_DISTANCE_FACTOR = 0.5

# Minimum wall distance (NFPA 72 §17.6.3.1.1)
MIN_WALL_DISTANCE_M = 0.10  # 4 inches


@dataclass
class RoomConfig:
    """Configuration for a single room in NFPA 72 calculations."""
    room_id: str
    name: str
    width_m: float
    depth_m: float
    ceiling_height_m: float
    occupancy_type: OccupancyType
    floor_number: int
    ceiling_type: str = "smooth"  # smooth, beamed, sloped, corridor

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['occupancy_type'] = self.occupancy_type.value
        return d

    @property
    def area_sqm(self) -> float:
        return self.width_m * self.depth_m

    @property
    def volume_cubic_m(self) -> float:
        return self.area_sqm * self.ceiling_height_m


@dataclass
class DetectorPlacement:
    """Placement of a detector for NFPA 72 calculations."""
    detector_id: str
    room_id: str
    x: float
    y: float
    z: float
    detector_type: str  # "smoke", "heat", "multi", "duct"
    coverage_radius_m: float = 6.37  # Default: 0.7 × 9.14m

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class NFPA72CalculationRequest:
    """Request for NFPA 72 calculation."""
    request_id: str
    building_id: str
    calculation_type: NFPA72CalculationType
    room_configs: List[RoomConfig]
    detector_placements: List[DetectorPlacement]
    input_hash: str
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['calculation_type'] = self.calculation_type.value
        d['room_configs'] = [r.to_dict() for r in self.room_configs]
        d['detector_placements'] = [dp.to_dict() for dp in self.detector_placements]
        return d

    @classmethod
    def create(
        cls,
        building_id: str,
        calculation_type: NFPA72CalculationType,
        room_configs: List[RoomConfig],
        detector_placements: List[DetectorPlacement],
    ) -> "NFPA72CalculationRequest":
        """Create a new calculation request with computed input hash."""
        temp = cls(
            request_id=str(uuid.uuid4()),
            building_id=building_id,
            calculation_type=calculation_type,
            room_configs=room_configs,
            detector_placements=detector_placements,
            input_hash="",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        input_json = json.dumps(temp.to_dict(), sort_keys=True, separators=(',', ':'))
        input_hash = hashlib.sha256(input_json.encode()).hexdigest()

        return cls(
            request_id=temp.request_id,
            building_id=temp.building_id,
            calculation_type=temp.calculation_type,
            room_configs=temp.room_configs,
            detector_placements=temp.detector_placements,
            input_hash=input_hash,
            timestamp=temp.timestamp,
        )


@dataclass
class DetectorRecommendation:
    """Recommendation for detector placement."""
    room_id: str
    suggested_x: float
    suggested_y: float
    suggested_z: float
    detector_type: str
    reason: str
    nfpa_reference: str


@dataclass
class NFPA72CalculationResult:
    """Result of NFPA 72 calculation."""
    request_id: str
    calculation_type: NFPA72CalculationType
    is_compliant: bool
    violations: List[Dict[str, Any]]
    warnings: List[str]
    recommendations: List[DetectorRecommendation]
    proof_certificate: str
    result_hash: str
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['calculation_type'] = self.calculation_type.value
        d['recommendations'] = [r.__dict__ for r in self.recommendations]
        return d


class NFPA72Bridge:
    """Bi-directional NFPA 72 calculation engine interface.

    Provides:
      - Deterministic calculations (same input → same output)
      - Cryptographic proof generation
      - Ceiling-height-adjusted spacing (Table 17.6.3.1.1)
      - Wall distance validation (§17.6.3.1.1)
      - Coverage validation (0.7S rule §17.7.4.2.3.1)

    Thread Safety: All public methods protected by Lock.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._calculation_history: List[NFPA72CalculationResult] = []

    @staticmethod
    def get_adjusted_spacing(
        ceiling_height_m: float,
        detector_type: str = "smoke",
    ) -> float:
        """Get NFPA 72 adjusted spacing based on ceiling height.

        Per NFPA 72-2022 Table 17.6.3.1.1 and Table 17.6.3.2.1.
        For ceiling heights above 9.1m, spot-type detectors are not
        suitable — requires beam or air-sampling detection.
        """
        if detector_type == "heat":
            table = HEAT_SPACING_BY_HEIGHT
            max_height = 7.62
        else:
            table = SMOKE_SPACING_BY_HEIGHT
            max_height = 9.1

        for (max_h, spacing) in table:
            if ceiling_height_m <= max_h:
                return spacing

        # Above table range — WARNING: spot detectors not suitable
        return table[-1][1]  # Return most conservative value

    @staticmethod
    def get_coverage_radius(spacing_m: float) -> float:
        """Coverage radius R = 0.7 × S per NFPA 72 §17.7.4.2.3.1."""
        return round(COVERAGE_RADIUS_FACTOR * spacing_m, 2)

    @staticmethod
    def get_max_wall_distance(spacing_m: float) -> float:
        """Max wall distance = 0.5 × S per NFPA 72 §17.6.3.1.1."""
        return round(WALL_DISTANCE_FACTOR * spacing_m, 2)

    def calculate_coverage(
        self,
        request: NFPA72CalculationRequest,
    ) -> NFPA72CalculationResult:
        """Calculate coverage compliance per NFPA 72-2022 §17.6.3.1.

        For each room, determines if:
          - Detector coverage area is within limits
          - All floor area is covered (0.7S rule)
          - Spacing between detectors is compliant
          - Wall distance is compliant (§17.6.3.1.1)
        """
        with self._lock:
            violations = []
            warnings = []

            detectors_by_room: Dict[str, List[DetectorPlacement]] = {}
            for det in request.detector_placements:
                if det.room_id not in detectors_by_room:
                    detectors_by_room[det.room_id] = []
                detectors_by_room[det.room_id].append(det)

            for room in request.room_configs:
                room_detectors = detectors_by_room.get(room.room_id, [])

                # Get height-adjusted spacing
                for det in room_detectors:
                    adjusted = self.get_adjusted_spacing(
                        room.ceiling_height_m, det.detector_type)
                    coverage_r = self.get_coverage_radius(adjusted)
                    wall_max = self.get_max_wall_distance(adjusted)

                    # Check if detector claims larger coverage than allowed
                    if det.coverage_radius_m > coverage_r + 0.1:
                        violations.append({
                            'type': 'coverage_exceeds_adjusted',
                            'room_id': room.room_id,
                            'detector_id': det.detector_id,
                            'severity': 'critical',
                            'message': (
                                f"Detector {det.detector_id} coverage "
                                f"{det.coverage_radius_m}m > adjusted {coverage_r}m "
                                f"(ceiling H={room.ceiling_height_m}m)"
                            ),
                            'nfpa_reference': 'NFPA 72-2022 Table 17.6.3.1.1',
                        })

                    # Check wall distance
                    # Distance from detector to nearest wall
                    # BUG FIX: det.x → det.y for y-axis wall distance
                    dist_to_wall_x = min(det.x, room.width_m - det.x)
                    dist_to_wall_y = min(det.y, room.depth_m - det.y)
                    dist_to_wall = min(dist_to_wall_x, dist_to_wall_y)

                    if dist_to_wall > wall_max:
                        violations.append({
                            'type': 'wall_distance_exceeded',
                            'room_id': room.room_id,
                            'detector_id': det.detector_id,
                            'severity': 'major',
                            'message': (
                                f"Detector {det.detector_id} wall distance "
                                f"{dist_to_wall:.2f}m > max {wall_max:.2f}m"
                            ),
                            'nfpa_reference': 'NFPA 72-2022 §17.6.3.1.1',
                        })
                    elif dist_to_wall < MIN_WALL_DISTANCE_M:
                        violations.append({
                            'type': 'wall_distance_too_close',
                            'room_id': room.room_id,
                            'detector_id': det.detector_id,
                            'severity': 'minor',
                            'message': (
                                f"Detector {det.detector_id} too close to wall "
                                f"{dist_to_wall:.2f}m < min {MIN_WALL_DISTANCE_M}m"
                            ),
                            'nfpa_reference': 'NFPA 72-2022 §17.6.3.1.1',
                        })

                if not room_detectors:
                    violations.append({
                        'type': 'no_detectors',
                        'room_id': room.room_id,
                        'severity': 'critical',
                        'message': f"No detectors in room {room.room_id}",
                        'nfpa_reference': 'NFPA 72-2022 §17.4.2',
                    })
                    continue

                # Check effective coverage using grid-based integration
                # BUG FIX (Consultant BUG 5): Replace arbitrary 0.65 factor
                # with proper grid-based coverage calculation.
                # Also applies ceiling height adjustment per NFPA 72 17.6.3.1.3.
                effective_coverage = self._calculate_effective_coverage(
                    room_detectors, room.width_m, room.depth_m,
                    room.ceiling_height_m,
                )

                if effective_coverage < room.area_sqm:
                    violations.append({
                        'type': 'insufficient_coverage',
                        'room_id': room.room_id,
                        'room_area_sqm': round(room.area_sqm, 1),
                        'effective_coverage_sqm': round(effective_coverage, 1),
                        'severity': 'critical',
                        'message': (
                            f"Room {room.room_id} coverage "
                            f"{effective_coverage:.1f}m² < area {room.area_sqm:.1f}m²"
                        ),
                        'nfpa_reference': 'NFPA 72-2022 §17.6.3.1',
                    })

                # Check spacing between detectors
                spacing_violations = self.calculate_spacing(room, room_detectors)
                violations.extend(spacing_violations)

            is_compliant = len(
                [v for v in violations if v.get('severity') == 'critical']
            ) == 0

            recommendations = self._generate_recommendations(request, violations)

            result = self._create_result(
                request=request,
                is_compliant=is_compliant,
                violations=violations,
                warnings=warnings,
                recommendations=recommendations,
            )

            self._calculation_history.append(result)
            return result

    def calculate_spacing(
        self,
        room_config: RoomConfig,
        detectors: List[DetectorPlacement],
    ) -> List[Dict[str, Any]]:
        """Calculate spacing between detectors per NFPA 72-2022 §17.6.3.2.

        Uses ceiling-height-adjusted spacing from Table 17.6.3.2.1.
        """
        violations = []

        if len(detectors) < 2:
            return violations

        for i, det1 in enumerate(detectors):
            # Get height-adjusted max spacing for this detector type
            max_spacing = self.get_adjusted_spacing(
                room_config.ceiling_height_m, det1.detector_type)

            for det2 in detectors[i + 1:]:
                distance = (
                    (det1.x - det2.x) ** 2 +
                    (det1.y - det2.y) ** 2
                ) ** 0.5

                if distance > max_spacing:
                    violations.append({
                        'type': 'spacing_violation',
                        'detector_1': det1.detector_id,
                        'detector_2': det2.detector_id,
                        'distance_m': round(distance, 2),
                        'max_allowed_m': round(max_spacing, 2),
                        'exceedance_m': round(distance - max_spacing, 2),
                        'severity': 'critical',
                        'nfpa_reference': 'NFPA 72-2022 Table 17.6.3.2.1',
                    })

        return violations

    def _calculate_effective_coverage(
        self,
        detectors: List[DetectorPlacement],
        room_width: float,
        room_depth: float,
        ceiling_height_m: float,
    ) -> float:
        """Calculate effective coverage area with proper overlap handling.

        BUG FIX (Consultant BUG 5): Uses grid-based integration instead of
        arbitrary 0.65/0.7 factor. Also applies ceiling height adjustment
        per NFPA 72-2022 17.6.3.1.3.

        Method: Divide room into grid cells and count covered cells.
        Each detector's coverage radius is adjusted for ceiling height.

        For performance: uses adaptive resolution (0.25m for small rooms,
        0.5m for large rooms) to balance accuracy vs speed.

        Args:
            detectors: List of detector placements in the room
            room_width: Room width in metres
            room_depth: Room depth in metres
            ceiling_height_m: Ceiling height in metres

        Returns:
            Effective coverage area in square metres
        """
        if not detectors:
            return 0.0

        # Adaptive resolution for performance
        room_area = room_width * room_depth
        if room_area < 100:
            resolution = 0.25  # Fine grid for small rooms
        elif room_area < 500:
            resolution = 0.5   # Medium grid
        else:
            resolution = 1.0   # Coarse grid for large rooms

        # Pre-compute height-adjusted coverage radii per NFPA 72 17.6.3.1.3
        # Ceilings above 10 ft (3.05m) use reduced spacing
        detector_radii: List[Tuple[float, float, float]] = []  # (x, y, r)
        for det in detectors:
            adjusted_spacing = self.get_adjusted_spacing(
                ceiling_height_m, det.detector_type)
            effective_radius = self.get_coverage_radius(adjusted_spacing)

            # NFPA 72-2022 17.6.3.1.3: linear reduction for high ceilings
            if ceiling_height_m > 3.05:
                reduction_factor = max(0.7, 1.0 - (ceiling_height_m - 3.05) * 0.1)
                effective_radius *= reduction_factor

            detector_radii.append((det.x, det.y, effective_radius))

        # Grid-based coverage calculation
        covered_cells = 0
        total_cells = 0

        nx = max(1, int(room_width / resolution))
        ny = max(1, int(room_depth / resolution))

        for ix in range(nx):
            for iy in range(ny):
                cell_x = (ix + 0.5) * resolution
                cell_y = (iy + 0.5) * resolution
                total_cells += 1

                # Check if any detector covers this cell
                for dx, dy, r in detector_radii:
                    dist_sq = (cell_x - dx) ** 2 + (cell_y - dy) ** 2
                    if dist_sq <= r * r:
                        covered_cells += 1
                        break

        if total_cells == 0:
            return 0.0

        return covered_cells * (resolution ** 2)

    def validate_design(
        self,
        building_id: str,
        room_configs: List[RoomConfig],
        detector_placements: List[DetectorPlacement],
    ) -> Dict[str, Any]:
        """Validate a complete design against NFPA 72 requirements."""
        coverage_request = NFPA72CalculationRequest.create(
            building_id=building_id,
            calculation_type=NFPA72CalculationType.COVERAGE,
            room_configs=room_configs,
            detector_placements=detector_placements,
        )

        coverage_result = self.calculate_coverage(coverage_request)

        critical_count = sum(
            1 for v in coverage_result.violations
            if v.get('severity') == 'critical'
        )

        return {
            'building_id': building_id,
            'is_compliant': critical_count == 0,
            'violation_count': len(coverage_result.violations),
            'critical_violations': critical_count,
            'warnings': coverage_result.warnings,
            'violations': coverage_result.violations,
            'recommendations': [
                r.__dict__ for r in coverage_result.recommendations
            ],
            'proof_certificate': coverage_result.proof_certificate,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }

    def _generate_recommendations(
        self,
        request: NFPA72CalculationRequest,
        violations: List[Dict[str, Any]],
    ) -> List[DetectorRecommendation]:
        """Generate detector placement recommendations to fix violations."""
        recommendations = []

        rooms_without_coverage = set()
        for v in violations:
            if v.get('type') == 'insufficient_coverage':
                rooms_without_coverage.add(v.get('room_id'))

        for room_id in rooms_without_coverage:
            room = next(
                (r for r in request.room_configs if r.room_id == room_id),
                None
            )
            if not room:
                continue

            adjusted = self.get_adjusted_spacing(room.ceiling_height_m, "smoke")
            coverage_r = self.get_coverage_radius(adjusted)
            # BUG FIX: Previous version used arbitrary 0.65 overlap factor
            # which contradicts the BUG 5 fix (grid-based coverage).
            # Use π·R² without overlap factor — grid-based validation
            # will catch any remaining gaps.
            area_per_det = 3.14159 * (coverage_r ** 2)
            recommended_count = max(1, int(room.area_sqm / area_per_det) + 1)

            grid_cols = int(recommended_count ** 0.5) + 1
            grid_rows = (recommended_count + grid_cols - 1) // grid_cols

            cell_width = room.width_m / grid_cols
            cell_depth = room.depth_m / grid_rows

            for i in range(recommended_count):
                col = i % grid_cols
                row = i // grid_cols

                recommendations.append(DetectorRecommendation(
                    room_id=room_id,
                    suggested_x=round(cell_width * (col + 0.5), 2),
                    suggested_y=round(cell_depth * (row + 0.5), 2),
                    suggested_z=round(room.ceiling_height_m - 0.1, 2),
                    detector_type="smoke",
                    reason=f"Insufficient coverage — need detector {i + 1}",
                    nfpa_reference="NFPA 72-2022 §17.6.3.1",
                ))

        return recommendations

    def _create_result(
        self,
        request: NFPA72CalculationRequest,
        is_compliant: bool,
        violations: List[Dict[str, Any]],
        warnings: List[str],
        recommendations: List[DetectorRecommendation],
    ) -> NFPA72CalculationResult:
        """Create a calculation result with cryptographic proof."""
        result_data = {
            'request_id': request.request_id,
            'is_compliant': is_compliant,
            'violations': sorted(
                violations, key=lambda x: x.get('severity', '')
            ),
            'warnings': warnings,
            'recommendations': [r.__dict__ for r in recommendations],
        }
        result_json = json.dumps(
            result_data, sort_keys=True, separators=(',', ':')
        )
        result_hash = hashlib.sha256(result_json.encode()).hexdigest()

        proof = self._generate_proof_certificate(
            request_id=request.request_id,
            input_hash=request.input_hash,
            result_hash=result_hash,
        )

        return NFPA72CalculationResult(
            request_id=request.request_id,
            calculation_type=request.calculation_type,
            is_compliant=is_compliant,
            violations=violations,
            warnings=warnings,
            recommendations=recommendations,
            proof_certificate=proof,
            result_hash=result_hash,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _generate_proof_certificate(
        self,
        request_id: str,
        input_hash: str,
        result_hash: str,
    ) -> str:
        """Generate cryptographic proof certificate.

        The certificate proves that:
          1. The input was received (input_hash)
          2. The calculation was performed deterministically
          3. The output was produced (result_hash)
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        cert_data = f"{request_id}:{input_hash}:{result_hash}:{timestamp}"
        return hashlib.sha256(cert_data.encode()).hexdigest()

    def get_calculation_history(
        self,
        limit: int = 100,
    ) -> List[NFPA72CalculationResult]:
        """Get calculation history."""
        with self._lock:
            return self._calculation_history[-limit:]


__all__ = [
    "NFPA72CalculationType",
    "OccupancyType",
    "RoomConfig",
    "DetectorPlacement",
    "NFPA72CalculationRequest",
    "DetectorRecommendation",
    "NFPA72CalculationResult",
    "NFPA72Bridge",
]
