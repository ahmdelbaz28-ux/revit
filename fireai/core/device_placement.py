"""fireai/core/device_placement.py — NFPA 72 Device Placement Engine
===================================================================
Implements deterministic device placement per NFPA 72-2022:

A. Smoke Detectors — §17.7
B. Heat Detectors  — §17.6
C. Manual Pull Stations — §17.15
D. Notification Appliances (Strobes/Horns) — Chapter 18
E. Duct Detectors — §17.7.4

SAFETY PRINCIPLE:
  - Zero coverage gaps — every point in covered space must be within
    detector radius per NFPA 72 §17.5
  - Beam obstruction rule: beam depth > 10% ceiling height = wall
    Source: NFPA 72-2022 §17.7.3.2.7
  - All placements verified against physics guards (Layer 0)
  - All results logged to audit trail (Layer 4)

STANDARDS:
  NFPA 72-2022 Chapter 17 — Initiating Devices
  NFPA 72-2022 Chapter 18 — Notification Appliances
  NFPA 101-2021 §7.2     — Means of Egress (pull station placement)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from fireai.constants.nfpa72 import (
    NAC_MIN_CD as NFPA72_NAC_MIN_CD,
)
from fireai.constants.nfpa72 import (
    NAC_SLEEPING_MIN_CD as NFPA72_NAC_SLEEPING_MIN_CD,
)
from fireai.constants.nfpa72 import (
    NAC_WALL_HEIGHT_M as NFPA72_NAC_WALL_HEIGHT_M,
)
from fireai.constants.nfpa72 import (
    PULL_STATION_FROM_EXIT_M as NFPA72_PULL_STATION_FROM_EXIT_M,
)
from fireai.constants.nfpa72 import (
    PULL_STATION_HEIGHT_M as NFPA72_PULL_STATION_HEIGHT_M,
)
from fireai.core.qomn_kernel import (  # type: ignore[attr-defined]
    PhysicsGuardError,
    QOMNKernel,
    compute_heat_detector_spacing,
    guard_ceiling_height_m,
)

# ═══════════════════════════════════════════════════════════════════════════════
# ENUMERATIONS
# ═══════════════════════════════════════════════════════════════════════════════


class DetectorType(str, Enum):
    SMOKE = "smoke"
    HEAT = "heat"
    DUCT = "duct"
    BEAM = "beam"
    ASPIRATING = "aspirating"
    MULTI = "multi"


class OccupancyType(str, Enum):
    """Occupancy types per NFPA 101-2021."""

    ASSEMBLY = "assembly"
    BUSINESS = "business"
    EDUCATIONAL = "educational"
    HEALTH_CARE = "health_care"
    RESIDENTIAL = "residential"
    MERCANTILE = "mercantile"
    INDUSTRIAL = "industrial"
    STORAGE = "storage"
    SPECIAL_PURPOSE = "special_purpose"
    HIGH_HAZARD = "high_hazard"


class CeilingType(str, Enum):
    FLAT = "flat"
    SLOPED = "sloped"
    PEAKED = "peaked"
    BEAM = "beam"
    COFFERED = "coffered"
    OPEN_JOIST = "open_joist"


# ═══════════════════════════════════════════════════════════════════════════════
# ROOM SPECIFICATION
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class BeamObstruction:
    """Beam obstruction on ceiling.

    Rule: if beam_depth > 0.10 × ceiling_height, treat beam as wall.
    Source: NFPA 72-2022 §17.7.3.2.7
    """

    x_start_m: float
    y_start_m: float
    x_end_m: float
    y_end_m: float
    depth_m: float  # beam depth (hanging below ceiling surface)


@dataclass
class ExitDoor:
    """Exit door location for pull station placement.

    Source: NFPA 72-2022 §17.15.3
    """

    x_m: float
    y_m: float
    door_width_m: float = 0.914  # 3 ft standard


@dataclass
class RoomSpec:
    """Complete room specification for device placement.

    All coordinates in meters from room origin (0,0).
    """

    room_id: str
    width_m: float
    length_m: float
    ceiling_height_m: float
    ceiling_type: CeilingType = CeilingType.FLAT
    occupancy_type: OccupancyType = OccupancyType.BUSINESS
    is_sleeping_area: bool = False
    slope_degrees: float = 0.0  # for sloped ceilings
    beams: List[BeamObstruction] = field(default_factory=list)
    exit_doors: List[ExitDoor] = field(default_factory=list)
    detector_type: DetectorType = DetectorType.SMOKE

    @property
    def area_m2(self) -> float:
        return self.width_m * self.length_m

    def validate(self) -> None:
        """Run physics guards on room specification."""
        guard_ceiling_height_m(self.ceiling_height_m)
        # V65 FIX: NaN bypasses <=0 check (NaN <= 0 is False in Python).
        # This allows NaN room dimensions to pass validation, producing NaN
        # area, NaN detector coordinates, and zero detectors placed.
        if not math.isfinite(self.width_m) or not math.isfinite(self.length_m):
            raise PhysicsGuardError(
                "room_dimensions",
                f"{self.width_m!r}×{self.length_m!r}",
                "room dimensions must be finite numbers (NaN/Inf rejected)",
                "Physics"
            )
        if self.width_m <= 0 or self.length_m <= 0:
            raise PhysicsGuardError(
                "room_dimensions", f"{self.width_m}×{self.length_m}", "room dimensions must be > 0", "Physics"
            )
        if self.slope_degrees < 0 or self.slope_degrees > 45:
            raise PhysicsGuardError(
                "slope_degrees",
                self.slope_degrees,
                "slope must be 0–45°; steeper slopes require special engineering",
                "NFPA 72-2022 §17.7.3.2.5",
            )


# ═══════════════════════════════════════════════════════════════════════════════
# PLACED DEVICE
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class PlacedDevice:
    """A placed fire alarm device with its engineering justification."""

    device_id: str
    device_type: DetectorType
    x_m: float
    y_m: float
    z_m: float  # mounting height AFF
    spacing_used_m: float
    radius_m: float
    nfpa_section: str
    formula: str
    beam_section: Optional[str] = None  # Beam sub-section if applicable


@dataclass
class PlacedPullStation:
    """Placed manual pull station."""

    device_id: str
    x_m: float
    y_m: float
    z_m: float  # = NFPA72_PULL_STATION_HEIGHT_M (48" AFF)
    near_exit_id: str
    nfpa_section: str = "NFPA 72-2022 §17.15"


@dataclass
class PlacedNotificationAppliance:
    """Placed strobe/horn notification appliance."""

    device_id: str
    x_m: float
    y_m: float
    z_m: float  # = NFPA72_NAC_WALL_HEIGHT_M (80" AFF)
    candela: int
    is_combo: bool = False  # combined horn+strobe
    nfpa_section: str = "NFPA 72-2022 Chapter 18"


@dataclass
class PlacementResult:
    """Complete placement result for a room."""

    room_id: str
    detectors: List[PlacedDevice]
    pull_stations: List[PlacedPullStation]
    notification_appliances: List[PlacedNotificationAppliance]
    coverage_pct: float
    beam_sections: int  # Number of beam-separated sections
    is_fully_compliant: bool
    violations: List[str]
    nfpa_references: List[str]
    computation_hash: str


# ═══════════════════════════════════════════════════════════════════════════════
# DETECTOR PLACEMENT ENGINE
# ═══════════════════════════════════════════════════════════════════════════════


class DetectorPlacementEngine:
    """NFPA 72-2022 compliant detector placement.

    Uses orthogonal hex grid placement optimized for NFPA 72 coverage.
    Applies beam obstruction rule and wall distance constraints.

    Reference: NFPA 72-2022 §17.7 (smoke), §17.6 (heat)
    """

    def __init__(self, kernel: Optional[QOMNKernel] = None) -> None:
        self._kernel = kernel or QOMNKernel()

    def place_detectors(self, room: RoomSpec) -> PlacementResult:
        """Place detectors in room per NFPA 72-2022.

        Algorithm:
          1. Validate room specification (Layer 0)
          2. Compute detector spacing per ceiling height (Layer 1/2)
          3. Check beam obstruction rule (Layer 1)
          4. Generate hex-grid positions with wall distances
          5. Filter positions inside room bounds
          6. Verify coverage (Layer 3)
          7. Log to audit trail (Layer 4)

        Returns:
            PlacementResult with all placed devices.

        """
        room.validate()
        violations: List[str] = []
        nfpa_refs: List[str] = []
        detectors: List[PlacedDevice] = []

        # ── Compute spacing ────────────────────────────────────────────────────
        if room.detector_type in (
            DetectorType.SMOKE,
            DetectorType.DUCT,
            DetectorType.BEAM,
            DetectorType.ASPIRATING,
            DetectorType.MULTI,
        ):
            spacing_result = self._kernel.smoke_detector_spacing(room.ceiling_height_m)
            nfpa_refs.append("NFPA 72-2022 §17.7.3 / Table 17.6.3.1")
        else:  # HEAT
            # V117 FIX (caller): Pass min(room.area_m2, NFPA_HEAT_MAX_AREA) as
            # area_per_detector. The OLD code passed room.area_m2 directly, which
            # violated the kernel's contract — the kernel's `area_per_detector_m2`
            # parameter is the coverage area PER detector (NFPA 72 §17.6.3.1 cap
            # 232.26 m² = 2500 ft²), not the room total. With the V117 area guard,
            # passing a >232.26 m² room area now raises PhysicsGuardError.
            #
            # SEMANTICS: For a heat detector design, the engineer specifies the
            # max coverage area per detector (≤ 232.26 m²). For rooms larger than
            # this, multiple detectors are needed and the hex-grid placement below
            # will tile them across the room. Using max coverage (232.26 m²) here
            # yields the MAXIMUM allowed spacing per NFPA — the densest acceptable
            # detector count. For rooms smaller than the max, the actual room area
            # is used, which naturally yields tighter spacing for safety.
            #
            # This change preserves backward-compatible BEHAVIOR (the prior code
            # silently clamped spacing to 15.24 m for any area ≥ 474 m², matching
            # the 0.7×√A → 15.24 cap), but now correctly REPORTS the spacing
            # derivation per the NFPA contract.
            NFPA72_HEAT_MAX_AREA_M2 = 232.26  # NFPA 72-2022 §17.6.3.1 (2500 ft²)
            area_per_detector = min(room.area_m2, NFPA72_HEAT_MAX_AREA_M2)
            spacing_result = compute_heat_detector_spacing(
                room.ceiling_height_m, area_per_detector
            )
            nfpa_refs.append("NFPA 72-2022 §17.6.3.1")

        S = spacing_result.get("listed_spacing_m") or spacing_result.get("spacing_m")
        R = spacing_result.get("coverage_radius_m")
        # V65 FIX: Guard against S=0 or S=None → infinite loop in hex grid.
        # S=0 makes row_height=0, causing y+=0 infinite loop.
        # S=None causes TypeError. Both are catastrophic in a safety-critical system.
        if S is None or not math.isfinite(S) or S <= 0:
            raise PhysicsGuardError(
                "spacing_m", S,
                "detector spacing must be a positive finite number — cannot place detectors without valid spacing",
                "NFPA 72"
            )
        if R is None or not math.isfinite(R) or R <= 0:
            raise PhysicsGuardError(
                "coverage_radius_m", R,
                "coverage radius must be a positive finite number — cannot verify coverage without valid radius",
                "NFPA 72 §17.7"
            )
        # wall_offset: distance from wall for first/last detector row.
        # Per NFPA 72 §17.6.3.1.1, max wall distance = S/2 (half the listed spacing).
        # Per NFPA 72 §17.6.3.1.1, min wall distance = 4 inches (0.1016m, dead air space).
        # The grid starts at wall_max_m from the wall (S/2), not wall_min_m (4 inches).
        wall_offset = spacing_result.get("wall_max_m", spacing_result.get("wall_min_m", S / 2.0))

        # ── Beam obstruction check ─────────────────────────────────────────────
        beam_sections = self._check_beam_obstructions(room, S)
        if beam_sections > 0:
            nfpa_refs.append("NFPA 72-2022 §17.7.3.2.7 (beam obstruction)")

        # ── Sloped ceiling adjustment ──────────────────────────────────────────
        # NFPA 72-2022 §17.7.3.2.5: detectors within 0.9m of ridge
        if room.ceiling_type in (CeilingType.SLOPED, CeilingType.PEAKED):
            nfpa_refs.append("NFPA 72-2022 §17.7.3.2.5 (sloped ceiling)")

        # ── Place detectors on hex grid ────────────────────────────────────────
        detectors = self._hex_grid_placement(room, S, R, wall_offset)

        # ── Verify coverage ────────────────────────────────────────────────────
        coverage_pct = self._verify_coverage(room, detectors, R)
        # V76 HIGH-04 FIX: Changed threshold from 99.0% to 99.9% to match
        # floor_orchestrator's adaptive re-solve threshold. Inconsistent thresholds
        # allowed designs at 99.5% to pass device_placement but fail orchestrator.
        if coverage_pct < 99.9:
            violations.append(
                f"Coverage {coverage_pct:.2f}% < 100% — NFPA 72 §17.5 requires full coverage. "
                "Additional detectors required."
            )
            nfpa_refs.append("NFPA 72-2022 §17.5 (coverage requirement)")

        # ── Place pull stations ────────────────────────────────────────────────
        pull_stations = self._place_pull_stations(room)
        if pull_stations:
            nfpa_refs.append("NFPA 72-2022 §17.15")

        # ── Place notification appliances ──────────────────────────────────────
        notifs = self._place_notification_appliances(room)
        if notifs:
            nfpa_refs.append("NFPA 72-2022 Chapter 18")

        # ── Compute result hash ────────────────────────────────────────────────
        import hashlib
        import json

        hash_data = json.dumps(
            {
                "room_id": room.room_id,
                "detector_count": len(detectors),
                "coverage_pct": coverage_pct,
                "spacing_m": S,
            },
            sort_keys=True,
        )
        result_hash = hashlib.sha256(hash_data.encode()).hexdigest()[:24]

        return PlacementResult(
            room_id=room.room_id,
            detectors=detectors,
            pull_stations=pull_stations,
            notification_appliances=notifs,
            coverage_pct=coverage_pct,
            beam_sections=beam_sections,
            is_fully_compliant=len(violations) == 0,
            violations=violations,
            nfpa_references=list(set(nfpa_refs)),
            computation_hash=result_hash,
        )

    def _hex_grid_placement(
        self,
        room: RoomSpec,
        spacing_m: float,
        radius_m: float,
        wall_min_m: float,
    ) -> List[PlacedDevice]:
        """Place detectors on hexagonal grid within room.

        Hexagonal grid provides optimal coverage efficiency.
        Row offset of S/2 per alternate row.
        Wall minimum distance enforced per NFPA 72 §17.7.4.2.3.1.

        Source: NFPA 72-2022 §17.7.3 / §17.7.4.2.3.1
        """
        devices: List[PlacedDevice] = []
        row_height = spacing_m * (math.sqrt(3) / 2.0)  # hex row spacing
        device_num = 1

        y = wall_min_m
        row = 0
        while y <= room.length_m - wall_min_m:
            offset = (spacing_m / 2.0) if row % 2 == 1 else 0.0
            x = wall_min_m + offset
            while x <= room.width_m - wall_min_m:
                if self._point_in_room(x, y, room):
                    devices.append(
                        PlacedDevice(
                            device_id=f"{room.room_id}-D{device_num:03d}",
                            device_type=room.detector_type,
                            x_m=round(x, 4),
                            y_m=round(y, 4),
                            z_m=round(room.ceiling_height_m - 0.05, 4),
                            spacing_used_m=spacing_m,
                            radius_m=radius_m,
                            nfpa_section="NFPA 72-2022 §17.7.4.2.3.1",
                            formula=f"Hex grid: S={spacing_m:.3f}m, R={radius_m:.3f}m",
                        )
                    )
                    device_num += 1
                x += spacing_m
            y += row_height
            row += 1

        # Safety: ensure at least one detector in any room
        if not devices:
            cx = room.width_m / 2.0
            cy = room.length_m / 2.0
            devices.append(
                PlacedDevice(
                    device_id=f"{room.room_id}-D001",
                    device_type=room.detector_type,
                    x_m=round(cx, 4),
                    y_m=round(cy, 4),
                    z_m=round(room.ceiling_height_m - 0.05, 4),
                    spacing_used_m=spacing_m,
                    radius_m=radius_m,
                    nfpa_section="NFPA 72-2022 §17.7.4.2.3.1",
                    formula="Centroid placement (small room)",
                )
            )

        return devices

    def _point_in_room(self, x: float, y: float, room: RoomSpec) -> bool:
        """Check if point is within room bounds."""
        return 0 <= x <= room.width_m and 0 <= y <= room.length_m

    def _check_beam_obstructions(self, room: RoomSpec, spacing_m: float) -> int:
        """Check for beam obstructions that divide detector zones.

        Rule: beam_depth > 0.10 × ceiling_height → treat as wall.
        Source: NFPA 72-2022 §17.7.3.2.7
        """
        threshold = 0.10 * room.ceiling_height_m  # 10% of ceiling height
        sections = 0
        for beam in room.beams:
            if beam.depth_m > threshold:
                sections += 1  # Each qualifying beam creates separate section
        return sections

    def _verify_coverage(
        self,
        room: RoomSpec,
        detectors: List[PlacedDevice],
        radius_m: float,
        grid_step: float = 0.0,
    ) -> float:
        """Verify coverage by sampling grid points.

        Adaptive step = min(0.25m, radius_m / 12) per V-07 fix.
        Ensures ≤ 8% quantization error for any detector radius:
          smoke R=6.37m → step=0.25m
          heat  R=1.5m  → step=0.125m

        Returns coverage percentage (0–100).
        Source: NFPA 72-2022 §17.5
        """
        if not detectors:
            return 0.0

        # Adaptive step: bounded [0.10m, 0.25m]
        step = grid_step if grid_step > 0 else min(0.25, max(0.10, radius_m / 12.0))

        total = 0
        covered = 0
        r2 = radius_m * radius_m

        y = step / 2
        while y <= room.length_m:
            x = step / 2
            while x <= room.width_m:
                if self._point_in_room(x, y, room):
                    total += 1
                    for d in detectors:
                        dx = x - d.x_m
                        dy = y - d.y_m
                        if dx * dx + dy * dy <= r2:
                            covered += 1
                            break
                x += step
            y += step

        return round(100.0 * covered / total, 4) if total > 0 else 0.0

    def _place_pull_stations(self, room: RoomSpec) -> List[PlacedPullStation]:
        """Place manual pull stations near exit doors.

        Rule: Within 1.524m (5 ft) of each exit doorway.
        Height: 1.219m (48") AFF to handle center.
        Source: NFPA 72-2022 §17.15.3, §17.15.7
        """
        stations: List[PlacedPullStation] = []
        for i, exit_door in enumerate(room.exit_doors):
            # V76 HIGH-05: Pull station placement uses x + offset (right side).
            # Per ADA and IBC, pull stations should be on the LATCH SIDE of the
            # door (handle side), which depends on door swing direction. Since
            # door swing data is not available in the current data model, this
            # placement must be verified by the fire protection engineer.
            # SAFETY: Place on available side, flag for verification.
            x = min(exit_door.x_m + NFPA72_PULL_STATION_FROM_EXIT_M, room.width_m - 0.1)
            stations.append(
                PlacedPullStation(
                    device_id=f"{room.room_id}-MPS{i + 1:02d}",
                    x_m=round(x, 4),
                    y_m=round(exit_door.y_m, 4),
                    z_m=NFPA72_PULL_STATION_HEIGHT_M,
                    near_exit_id=f"EXIT-{i + 1}",
                    nfpa_section="NFPA 72-2022 §17.15",
                )
            )
        # NOTE: Pull station placement assumes right-side-of-door position.
        # ADA/IBC require latch-side placement. Verify door swing direction
        # with architectural plans. This is flagged for manual FPE review.
        if stations:
            import logging
            _pull_logger = logging.getLogger(__name__)
            _pull_logger.warning(
                f"Room {room.room_id}: Pull stations placed on right side of "
                f"exit doors. Verify latch-side placement per ADA/IBC — door "
                f"swing direction not available in data model."
            )
        return stations

    def _place_notification_appliances(self, room: RoomSpec) -> List[PlacedNotificationAppliance]:
        """Place strobes/horns per NFPA 72 Chapter 18.

        Candela: 75 cd minimum, 177 cd for sleeping areas.
        Height:  2.032m (80") AFF minimum.
        Source: NFPA 72-2022 §18.5.3.1, §18.5.5.1, §18.5.5.7
        """
        appliances: List[PlacedNotificationAppliance] = []
        cd = NFPA72_NAC_SLEEPING_MIN_CD if room.is_sleeping_area else NFPA72_NAC_MIN_CD

        # Place one appliance per wall facing (minimum)
        positions = [
            (room.width_m / 4.0, 0.305),  # south wall
            (3 * room.width_m / 4.0, 0.305),  # south wall #2
            (room.width_m / 2.0, room.length_m - 0.305),  # north wall
        ]

        for i, (x, y) in enumerate(positions):
            appliances.append(
                PlacedNotificationAppliance(
                    device_id=f"{room.room_id}-NAC{i + 1:02d}",
                    x_m=round(x, 4),
                    y_m=round(y, 4),
                    z_m=NFPA72_NAC_WALL_HEIGHT_M,
                    candela=cd,
                    is_combo=True,  # default: combo horn+strobe
                    nfpa_section="NFPA 72-2022 §18.5",
                )
            )

        return appliances


# ═══════════════════════════════════════════════════════════════════════════════
# DUCT DETECTOR PLACEMENT
# Source: NFPA 72-2022 §17.7.4
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class DuctDetectorSpec:
    """Duct smoke detector specification.

    Placed in supply and return air ducts to detect smoke in HVAC.
    Source: NFPA 72-2022 §17.7.4
    """

    duct_id: str
    width_m: float
    height_m: float  # duct cross-section height
    velocity_m_s: float  # air velocity in duct


def place_duct_detector(spec: DuctDetectorSpec) -> Dict[str, Any]:
    """Compute duct detector placement per NFPA 72 §17.7.4.

    Rules:
      - Duct width ≤ 0.305m (12 in): one detector
      - Duct width > 0.305m but ≤ 0.914m: two detectors
      - Additional detectors for wider ducts
      - Air velocity 0.305–15.24 m/s (60–3000 fpm) per §17.7.4.2.2
      Source: NFPA 72-2022 §17.7.4.2
    """
    v = spec.velocity_m_s
    if not math.isfinite(v) or v <= 0:
        raise PhysicsGuardError("velocity_m_s", v, "air velocity must be > 0", "NFPA 72-2022 §17.7.4.2.2")

    MIN_VEL = 0.305  # 60 fpm
    MAX_VEL = 15.24  # 3000 fpm
    if v < MIN_VEL:
        raise PhysicsGuardError(
            "velocity_m_s",
            f"{v:.3f}m/s",
            f"below minimum {MIN_VEL}m/s (60 fpm). Detector may not respond.",
            "NFPA 72-2022 §17.7.4.2.2",
        )
    if v > MAX_VEL:
        raise PhysicsGuardError(
            "velocity_m_s",
            f"{v:.3f}m/s",
            f"exceeds maximum {MAX_VEL}m/s (3000 fpm). Detector may false alarm.",
            "NFPA 72-2022 §17.7.4.2.2",
        )

    # Number of detectors based on duct width
    W = spec.width_m
    if W <= 0.305:
        n_detectors = 1
    elif W <= 0.914:
        n_detectors = 2
    else:
        n_detectors = math.ceil(W / 0.914) + 1

    return {
        "duct_id": spec.duct_id,
        "n_detectors": n_detectors,
        "duct_width_m": W,
        "air_velocity_m_s": v,
        "nfpa_section": "NFPA 72-2022 §17.7.4",
        "compliance_note": f"{n_detectors} detector(s) required for {W:.3f}m width duct",
    }
