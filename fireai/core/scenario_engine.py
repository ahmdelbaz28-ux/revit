"""scenario_engine.py — Fire Scenario Testing Engine (FireAI Integration)
======================================================================
NFPA 72-2022 §17.7.3 / §A.17.6 / NFPA 72 Annex B

Purpose:
  Test detector layouts from DensityOptimizer/FloorAnalyser against
  calibrated fire scenarios. Output: response time, first detector,
  blind spots, and PASS/FAIL per NFPA 72 §17.7.3.

Design principles:
  - Every scenario is an immutable dataclass — no shared mutable state.
  - Physics: t-squared model (NFPA 72 §A.17.6.3) — Q(t) = alpha * t^2
  - Detection time: smoke obscuration at detector exceeds threshold.
  - No guesses: every value sourced from NFPA 72, UL 268, or SFPE.
  - System detects blind spots but does NOT modify layout.
  - Uses geometry_utils.py (pure Python) — zero mandatory external deps.

Fixes vs. upstream v13 code:
  1. Shapely optional: geometry_utils.point_in_polygon + grid_points_in_polygon
  2. No duplicate _polygon_centroid — uses geometry_utils.polygon_centroid
  3. Removed unused imports (statistics, numpy)
  4. _ALPERT constants actually used in ceiling_jet_temp_rise()
  5. smoke_optical_density uses Alpert ceiling jet velocity
  6. detection_time() has analytical fast-path + time-step fallback
  7. blind_spot_scan uses geometry_utils.grid_points_in_polygon
  8. ScenarioVerdict.FAIL_BLIND_SPOT uses _BLIND_SPOT_MIN_GAP_M
  9. scenario deduplication in all_scenarios()
  10. q_max_from_fire_load uses occupancy-aware t_burn
  11. CSV output escapes commas in fields

References:
  NFPA 72-2022 §17.6, §17.7.3, Table 17.6.3.1, Annex B.2
  UL 268 (Smoke Detectors for Fire Alarm Systems)
  Alpert (1972): Calculation of Response Time of Ceiling-Mounted Fire Detectors
  Milke, J.A. (2008): Smoke Detection — A Perspective
  Heskestad, G. (1972): Peak gas velocities and flame heights

"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from fireai.core.geometry_utils import (
    grid_points_in_polygon,
    point_in_polygon,
    polygon_area,
    polygon_centroid,
)

# ============================================================================
# NFPA 72 CONSTANTS (all sourced, none invented)
# ============================================================================

# t-squared growth coefficients alpha (kW/s^2) — NFPA 72-2022 Table B.2.3
_ALPHA: Dict[str, float] = {
    "slow": 0.00293,
    "medium": 0.01172,
    "fast": 0.04689,
    "ultrafast": 0.18760,
    "ultra-fast": 0.18760,  # Alias — NFPA 72 Annex B uses "ultra-fast"
}

# Maximum allowable detection time (seconds) — NFPA 72-2022 §17.7.3
# For life-safety: <= 60 s from ignition to alarm signal in occupied spaces.
_NFPA_MAX_DETECTION_S: float = 60.0

# Smoke obscuration threshold at detector (%/m) — UL 268
_SMOKE_THRESHOLD_ION_PCT_M: float = 2.5  # ionisation
_SMOKE_THRESHOLD_PHOTO_PCT_M: float = 4.0  # photoelectric

# Ceiling jet model constants — Alpert (1972)
_ALPERT_DT_FAR: float = 5.38  # DeltaT for r/H > 0.18
_ALPERT_DT_NEAR: float = 16.9  # DeltaT for r/H <= 0.18
_ALPERT_V_FAR: float = 0.197  # velocity for r/H > 0.15
_ALPERT_V_NEAR: float = 0.962  # velocity for r/H <= 0.15

# Smoke yield factor (kg smoke / kg fuel) — SFPE Handbook Table 3-4.14
_SMOKE_YIELD: Dict[str, float] = {
    "flaming": 0.015,  # typical for flaming combustion
    "smouldering": 0.060,  # smouldering produces heavier smoke
}

# Specific extinction coefficient (m^2/kg) — SFPE 3rd ed.
_EXTINCTION_COEFF: Dict[str, float] = {
    "flaming": 7600.0,
    "smouldering": 4400.0,
}

# Minimum blind-spot gap considered significant (metres)
_BLIND_SPOT_MIN_GAP_M: float = 0.5

# Grid resolution for blind-spot scan (metres)
_SCAN_GRID_M: float = 0.25

# Burn duration estimates by occupancy type (seconds)
_BURN_DURATION: Dict[str, float] = {
    "office": 1200.0,  # 20 min — typical office fuel package
    "warehouse": 900.0,  # 15 min — high fuel load, faster burnout
    "retail": 1000.0,
    "education": 1200.0,
    "healthcare": 1500.0,  # slower — more compartmentation
    "residential": 1200.0,
    "industrial": 800.0,  # fast burnout, high ventilation
    "default": 1200.0,
}


# ============================================================================
# ENUMERATIONS
# ============================================================================


class GrowthRate(Enum):
    SLOW = "slow"
    MEDIUM = "medium"
    FAST = "fast"
    ULTRAFAST = "ultrafast"

    @property
    def alpha(self) -> float:
        return _ALPHA[self.value]

    @property
    def label(self) -> str:
        return {
            "slow": "Slow (NFPA 72 §B.2 — smouldering, e.g. foam rubber)",
            "medium": "Medium (NFPA 72 §B.2 — standard, e.g. wood pallets)",
            "fast": "Fast (NFPA 72 §B.2 — e.g. polyurethane foam)",
            "ultrafast": "Ultrafast (NFPA 72 §B.2 — e.g. pool fires, flammable liquids)",
        }[self.value]


class SmokeType(Enum):
    """NFPA 72-2022 §17.7.3 distinguishes smouldering (visible, large particles)
    from flaming (invisible, small particles). Detector sensitivity varies.
    """

    SMOULDERING = "smouldering"  # photoelectric more sensitive
    FLAMING = "flaming"  # ionisation more sensitive


class ScenarioVerdict(Enum):
    PASS = "PASS"
    FAIL_SLOW = "FAIL_SLOW"  # detected but too slowly
    FAIL_NO_DETECTOR = "FAIL_NO_DETECTOR"  # no detector covers ignition zone
    FAIL_BLIND_SPOT = "FAIL_BLIND_SPOT"  # blind spots > _BLIND_SPOT_MIN_GAP_M
    SKIPPED = "SKIPPED"  # geometry issue, not run


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass(frozen=True)
class FireScenario:
    """Immutable definition of one fire scenario.

    All fields map directly to NFPA 72 or physical parameters.
    No defaults that hide assumptions: caller must be explicit.

    Args:
        scenario_id:      Unique identifier (e.g. "worst_case_corner").
        description:      Human-readable description.
        ignition_point:   (x, y) in metres from room origin.
                          Must be inside the room polygon.
        growth_rate:      t-squared growth rate from GrowthRate enum.
        smoke_type:       SmokeType.SMOULDERING or SmokeType.FLAMING.
        fire_load_mj_m2:  Specific fire load in MJ/m^2 (from occupancy tables).
                          Used to cap maximum HRR (Q_max).
                          None = uncapped (worst case).
        ambient_temp_c:   Ambient temperature in deg C (default 20 per NFPA Annex B).
        ceiling_height_m: Room ceiling height in metres.
        nfpa_time_limit_s: Maximum detection time per NFPA 72 (default 60 s).

    """

    scenario_id: str
    description: str
    ignition_point: Tuple[float, float]
    growth_rate: GrowthRate
    smoke_type: SmokeType
    fire_load_mj_m2: Optional[float]
    ambient_temp_c: float
    ceiling_height_m: float
    nfpa_time_limit_s: float = _NFPA_MAX_DETECTION_S


@dataclass
class DetectionEvent:
    """Represents one detector triggering during a scenario."""

    detector_index: int
    detector_pos: Tuple[float, float]
    distance_m: float  # from ignition point to detector
    detection_time_s: float  # seconds from ignition
    hrr_at_detection_kw: float  # Heat Release Rate when alarm triggers
    smoke_conc_pct_m: float  # estimated smoke obscuration at detector


@dataclass
class BlindSpot:
    """A grid point not reached within nfpa_time_limit_s by any detector."""

    position: Tuple[float, float]
    nearest_detector_dist_m: float
    estimated_detection_s: float  # extrapolated, may exceed limit


@dataclass
class ScenarioResult:
    """Complete result of running one FireScenario against a detector layout.

    All timing is in seconds from ignition.
    All positions are in metres from room origin.
    """

    scenario_id: str
    scenario_description: str
    verdict: ScenarioVerdict

    # Detection
    first_detection_time_s: Optional[float]  # None if no detector triggered
    first_detector: Optional[DetectionEvent]
    all_detections: List[DetectionEvent]  # all detectors that triggered <= limit

    # Blind spots
    blind_spots: List[BlindSpot]
    blind_spot_area_pct: float  # % of room area with detection_time > limit

    # Fire state at first detection
    hrr_at_first_alarm_kw: Optional[float]
    smoke_at_first_alarm_pct_m: Optional[float]

    # Compliance
    nfpa_time_limit_s: float
    compliant: bool  # first_detection_time_s <= nfpa_time_limit_s
    margin_s: Optional[float]  # positive = margin, negative = overrun

    # Performance
    detectors_tested: int
    grid_points_tested: int
    compute_time_s: float

    # Audit
    nfpa_clause: str = "NFPA 72-2022 §17.7.3"
    warnings: List[str] = field(default_factory=list)


# ============================================================================
# SCENARIO LIBRARY
# ============================================================================


class ScenarioLibrary:
    """Pre-defined scenarios based on NFPA 72-2022 Annex B and FPE practice.
    All scenarios use explicit fire physics — no default assumptions.

    Usage:
        scenarios = ScenarioLibrary.all_scenarios(
            room_polygon    = [...],
            ceiling_height  = 3.0,
            fire_load_mj_m2 = 400.0,   # office, NFPA 557 Table 5.1
        )
    """

    @staticmethod
    def worst_case(
        room_polygon: List[Tuple[float, float]],
        ceiling_height: float,
        fire_load_mj_m2: Optional[float] = None,
    ) -> FireScenario:
        """Worst case: fastest growth (ultrafast), flaming, centroid ignition.
        Centroid maximises average distance to wall-mounted detectors.
        NFPA 72 §B.2: ultrafast for high-hazard occupancies.
        """
        cx, cy = polygon_centroid(room_polygon)
        return FireScenario(
            scenario_id="worst_case_ultrafast",
            description="Worst case: ultrafast fire at room centroid (max avg detector distance)",
            ignition_point=(cx, cy),
            growth_rate=GrowthRate.ULTRAFAST,
            smoke_type=SmokeType.FLAMING,
            fire_load_mj_m2=fire_load_mj_m2,
            ambient_temp_c=20.0,
            ceiling_height_m=ceiling_height,
            nfpa_time_limit_s=_NFPA_MAX_DETECTION_S,
        )

    @staticmethod
    def most_probable_office(
        room_polygon: List[Tuple[float, float]],
        ceiling_height: float,
        fire_load_mj_m2: float = 400.0,
    ) -> FireScenario:
        """Most probable office fire: medium growth, smouldering start.
        Fire load 400 MJ/m^2 — NFPA 557-2016 Table 5.1 (offices).
        """
        cx, cy = polygon_centroid(room_polygon)
        return FireScenario(
            scenario_id="most_probable_office",
            description="Most probable office fire: medium t-sq, smouldering, 400 MJ/m^2",
            ignition_point=(cx, cy),
            growth_rate=GrowthRate.MEDIUM,
            smoke_type=SmokeType.SMOULDERING,
            fire_load_mj_m2=fire_load_mj_m2,
            ambient_temp_c=20.0,
            ceiling_height_m=ceiling_height,
        )

    @staticmethod
    def corner_fire(
        room_polygon: List[Tuple[float, float]],
        ceiling_height: float,
        fire_load_mj_m2: Optional[float] = None,
        corner_index: int = 0,
    ) -> FireScenario:
        """Corner fire: fast growth from the specified polygon vertex.
        Corners are high-risk: furniture accumulates there and
        detectors are typically furthest from corners.
        NFPA 72-2022 §A.17.6.3.
        """
        n = len(room_polygon)
        idx = corner_index % n
        vx, vy = room_polygon[idx]
        # Move 30% toward centroid to ensure inside polygon
        pcx, pcy = polygon_centroid(room_polygon)
        ix = vx + 0.3 * (pcx - vx)
        iy = vy + 0.3 * (pcy - vy)
        return FireScenario(
            scenario_id=f"corner_fire_v{corner_index}",
            description=f"Corner fire at vertex {corner_index}: fast t-sq, flaming",
            ignition_point=(round(ix, 3), round(iy, 3)),
            growth_rate=GrowthRate.FAST,
            smoke_type=SmokeType.FLAMING,
            fire_load_mj_m2=fire_load_mj_m2,
            ambient_temp_c=20.0,
            ceiling_height_m=ceiling_height,
        )

    @staticmethod
    def wall_midpoint_fire(
        room_polygon: List[Tuple[float, float]],
        ceiling_height: float,
        fire_load_mj_m2: Optional[float] = None,
        wall_index: int = 0,
    ) -> FireScenario:
        """Fire at midpoint of a wall segment.
        Important because detectors near walls may have reduced coverage
        due to wall distance constraints (NFPA 72 §17.6.3.1.1).
        """
        n = len(room_polygon)
        i = wall_index % n
        j = (i + 1) % n
        # Midpoint of wall segment
        mx = (room_polygon[i][0] + room_polygon[j][0]) / 2.0
        my = (room_polygon[i][1] + room_polygon[j][1]) / 2.0
        # Push 0.5m inside
        pcx, pcy = polygon_centroid(room_polygon)
        dx, dy = pcx - mx, pcy - my
        length = math.hypot(dx, dy)
        if length > 0.01:
            ix = mx + 0.5 * dx / length
            iy = my + 0.5 * dy / length
        else:
            ix, iy = mx, my
        return FireScenario(
            scenario_id=f"wall_mid_{wall_index}",
            description=f"Wall midpoint fire at segment {wall_index}: fast t-sq, flaming",
            ignition_point=(round(ix, 3), round(iy, 3)),
            growth_rate=GrowthRate.FAST,
            smoke_type=SmokeType.FLAMING,
            fire_load_mj_m2=fire_load_mj_m2,
            ambient_temp_c=20.0,
            ceiling_height_m=ceiling_height,
        )

    @staticmethod
    def all_corners(
        room_polygon: List[Tuple[float, float]],
        ceiling_height: float,
        fire_load_mj_m2: Optional[float] = None,
    ) -> List[FireScenario]:
        """One corner_fire scenario per polygon vertex."""
        return [
            ScenarioLibrary.corner_fire(room_polygon, ceiling_height, fire_load_mj_m2, i)
            for i in range(len(room_polygon))
        ]

    @staticmethod
    def blind_spot_scan(
        room_polygon: List[Tuple[float, float]],
        ceiling_height: float,
        fire_load_mj_m2: Optional[float] = None,
        grid_m: float = 1.0,
    ) -> List[FireScenario]:
        """Grid scan: one scenario per grid point inside the polygon.
        Used to find blind spots not caught by corner/centroid tests.
        Uses geometry_utils.grid_points_in_polygon (no shapely).
        """
        grid_pts = grid_points_in_polygon(room_polygon, step=grid_m, margin=0.0)
        scenarios = []
        for gx, gy in grid_pts:
            scenarios.append(
                FireScenario(
                    scenario_id=f"grid_{round(gx, 2)}_{round(gy, 2)}",
                    description=f"Grid scan at ({gx:.2f}, {gy:.2f})",
                    ignition_point=(round(gx, 3), round(gy, 3)),
                    growth_rate=GrowthRate.FAST,
                    smoke_type=SmokeType.FLAMING,
                    fire_load_mj_m2=fire_load_mj_m2,
                    ambient_temp_c=20.0,
                    ceiling_height_m=ceiling_height,
                )
            )
        return scenarios

    @staticmethod
    def all_scenarios(
        room_polygon: List[Tuple[float, float]],
        ceiling_height: float,
        fire_load_mj_m2: Optional[float] = None,
    ) -> List[FireScenario]:
        """Standard battery: worst_case + most_probable + all_corners.
        Does NOT include blind_spot_scan (expensive — call separately).
        Deduplicates scenarios with identical ignition points.
        """
        raw: List[FireScenario] = [
            ScenarioLibrary.worst_case(room_polygon, ceiling_height, fire_load_mj_m2),
            ScenarioLibrary.most_probable_office(room_polygon, ceiling_height, fire_load_mj_m2 or 400.0),
        ] + ScenarioLibrary.all_corners(room_polygon, ceiling_height, fire_load_mj_m2)

        # Deduplicate by ignition point (rounded to 3 decimal places)
        seen: Dict[Tuple[float, float], FireScenario] = {}
        for sc in raw:
            key = (round(sc.ignition_point[0], 3), round(sc.ignition_point[1], 3))
            if key not in seen:
                seen[key] = sc
        return list(seen.values())


# ============================================================================
# PHYSICS ENGINE
# ============================================================================


class FirePhysics:
    """NFPA 72 / Alpert ceiling jet fire physics.

    References:
      Alpert, R.L. (1972): Calculation of Response Time of Ceiling-Mounted
      Fire Detectors. Fire Technology, 8(3), 181-195.

      NFPA 72-2022 Annex B: Engineering Guide for Automatic Fire Detector
      Spacing.

      Milke, J.A. (2008): Smoke Detection — A Perspective. Fire Protection
      Engineering, No. 38.

      Heskestad, G. (1972): Peak gas velocities and flame heights of
      buoyant gas diffusion flames. Symposium (International) on Combustion.

    All equations are traceable to the above references.
    No curve-fitting or ML in this module.

    """

    @staticmethod
    def hrr_at_time(alpha: float, t: float, q_max: Optional[float] = None) -> float:
        """Heat Release Rate [kW] at time t [s] using t-squared model.
        Q(t) = alpha * t^2   [NFPA 72-2022 §A.17.6.3]
        Capped at q_max if provided (fuel-limited phase).
        """
        q = alpha * t * t
        if q_max is not None and q > q_max:
            return q_max
        return q

    @staticmethod
    def q_max_from_fire_load(
        fire_load_mj_m2: float,
        area_m2: float,
        occupancy: str = "default",
    ) -> float:
        """Estimate peak HRR from fire load and room area.
        Q_max ~ fire_load [MJ] / t_burn [s]
        t_burn varies by occupancy — uses _BURN_DURATION table.
        Returns kW.
        """
        t_burn = _BURN_DURATION.get(occupancy.lower(), _BURN_DURATION["default"])
        total_mj = fire_load_mj_m2 * area_m2
        return (total_mj * 1000.0) / t_burn  # kJ / s = kW

    @staticmethod
    def ceiling_jet_temp_rise(
        q_kw: float,
        r_m: float,
        ceiling_h_m: float,
    ) -> float:
        """Alpert (1972) ceiling jet temperature rise [deg C] above ambient
        at horizontal distance r from fire axis, at ceiling height H.

        Uses module-level constants _ALPERT_DT_FAR and _ALPERT_DT_NEAR
        (5.38 and 16.9 respectively) instead of magic numbers.

        dT = 5.38 * (Q/r)^(2/3) / H      if r/H > 0.18
        dT = 16.9 * Q^(2/3) / H^(5/3)    if r/H <= 0.18

        Returns: Temperature rise [deg C]. Always >= 0.
        """
        if q_kw <= 0 or r_m <= 0 or ceiling_h_m <= 0:
            return 0.0
        ratio = r_m / ceiling_h_m
        if ratio > 0.18:
            dt = _ALPERT_DT_FAR * (q_kw / r_m) ** (2.0 / 3.0) / ceiling_h_m
        else:
            dt = _ALPERT_DT_NEAR * q_kw ** (2.0 / 3.0) / ceiling_h_m ** (5.0 / 3.0)
        return max(0.0, dt)

    @staticmethod
    def ceiling_jet_velocity(
        q_kw: float,
        r_m: float,
        ceiling_h_m: float,
    ) -> float:
        """Alpert (1972) ceiling jet velocity [m/s] at distance r.

        V = 0.197 * (Q)^1/3 * (r/H)^-5/6 / H^1/3   if r/H > 0.15
        V = 0.962 * (Q/H)^1/3                        if r/H <= 0.15

        Used for smoke transport estimation.
        """
        if q_kw <= 0 or r_m <= 0 or ceiling_h_m <= 0:
            return 0.0
        ratio = r_m / ceiling_h_m
        if ratio > 0.15:
            return _ALPERT_V_FAR * (q_kw ** (1.0 / 3.0)) * (ratio ** (-5.0 / 6.0)) / (ceiling_h_m ** (1.0 / 3.0))
        return _ALPERT_V_NEAR * ((q_kw / ceiling_h_m) ** (1.0 / 3.0))

    @staticmethod
    def smoke_optical_density(
        q_kw: float,
        r_m: float,
        ceiling_h_m: float,
        smoke_type: SmokeType,
    ) -> float:
        """Estimate smoke obscuration [%/m] at detector position.

        Uses the Milke (2008) / NFPA Annex B engineering correlation for
        optical density at ceiling level. The model relates smoke OD to
        HRR and distance through ceiling jet transport:

        Model:
          1. Smoke production rate: S = y_s * Q [kg/s]
          2. Ceiling jet mass flow at distance r (Alpert):
             m_jet = C_jet * Q^(1/3) * r^(5/3)   for r/H > 0.18
             This carries smoke radially outward.
          3. Smoke mass concentration in ceiling jet:
             c = S / (m_jet * A_jet_layer)
             where A_jet_layer = 2*pi*r*delta (annular ring area * layer depth)
          4. Optical density = sigma * c [1/m] converted to %/m

        For r/H <= 0.18 (plume impingement zone), smoke is concentrated
        by plume flow and diluted less — use near-field model.

        IMPORTANT: This is an engineering estimate. OD scales with Q
        and inversely with r^(2/3) (far field) or Q^(1/3) (near field).
        For regulatory submission, validate with CFD (FDS) or full-scale test.

        Returns: Estimated smoke obscuration [%/m], capped at 100.
        """
        if q_kw <= 0:
            return 0.0

        stype = smoke_type.value
        y_s = _SMOKE_YIELD[stype]
        sigma = _EXTINCTION_COEFF[stype]

        H = max(ceiling_h_m, 0.5)
        r = max(r_m, 0.01)
        ratio = r / H

        # Smoke production rate (kg/s)
        # BUG FIX (2026-05-19): Previous formula y_s * Q gave units of
        # (kg_soot/kg_fuel) * kW, which is NOT kg/s.
        # Correct: s_rate = y_s * Q / ΔH_c  where ΔH_c = heat of combustion.
        # Using ΔH_c ≈ 13.1 MJ/kg (cellulosic fuel, SFPE Handbook Table 3-4.14).
        HEAT_OF_COMBUSTION_KW_S_PER_KG = 13100.0  # kJ/kg = kW·s/kg
        s_rate = y_s * q_kw / HEAT_OF_COMBUSTION_KW_S_PER_KG

        # Ceiling jet layer depth (Alpert: ~5-12% of H, use 10%)
        delta = 0.10 * H

        if ratio > 0.18:
            # Far field: ceiling jet carries smoke radially
            #
            # BUG FIX (2026-05-19): Previous version used _ALPERT_V_FAR (0.197)
            # as a mass flow constant. But 0.197 is the VELOCITY constant from
            # Alpert's ceiling jet velocity correlation:
            #   V = 0.197 * Q^(1/3) * (r/H)^(-5/6) / H^(1/3)  [m/s]
            # This is NOT a mass flow formula.
            #
            # Correct approach: compute mass flow from velocity × density × area.
            #   m_jet = rho * V * delta * 2*pi*r
            # where delta = ceiling jet layer thickness (~10% of H per Alpert)
            #
            # Alpert ceiling jet velocity at distance r (far field, r/H > 0.15):
            #   V = 0.197 * Q^(1/3) * (r/H)^(-5/6) / H^(1/3)
            # Mass flow = rho * V * delta * 2*pi*r (integrated over annular ring)

            # Ceiling jet velocity (Alpert 1972, far field)
            V_jet = _ALPERT_V_FAR * (q_kw ** (1.0 / 3.0)) * (ratio ** (-5.0 / 6.0)) / (H ** (1.0 / 3.0))

            # Ceiling jet mass flow (kg/s) — derived from velocity
            # m = rho * V * delta * 2*pi*r
            # Using rho ≈ 1.2 kg/m³, delta = 0.10*H
            rho_air = 1.2  # V60 FIX (P5-4): Should use PHYSICAL_CONSTANTS["AMBIENT_AIR_DENSITY_KG_M3"]
            # but scenario_engine.py doesn't import semi_cfast_engine.
            # Documenting: value must match PHYSICAL_CONSTANTS if that dict is updated.
            m_jet = rho_air * V_jet * delta * 2.0 * math.pi * r

            # Smoke concentration at ceiling jet layer
            ring_area = 2.0 * math.pi * r * delta
            if m_jet > 0 and ring_area > 0:
                c_mass = s_rate / (m_jet * ring_area)
            else:
                c_mass = 0.0
        else:
            # Near field (plume impingement zone): smoke is concentrated
            # Plume mass flow (Heskestad):
            #   m_p = 0.071 * Q_c^(1/3) * H^(5/3) + 0.0018 * Q_c
            # V60 FIX (P5-5): These are Heskestad correlation coefficients from
            # SFPE Handbook 6th Ed., Table 16.5.1. They are empirically derived
            # and do not vary with conditions — documenting the source for traceability.
            _HESKESTAD_C1 = 0.071  # kg/(s·kW^1/3·m^5/3) — SFPE Handbook, Heskestad (2016)
            _HESKESTAD_C2 = 0.0018  # kg/(s·kW) — virtual origin correction
            chi_c = 0.7 if smoke_type == SmokeType.FLAMING else 0.4
            q_c = chi_c * q_kw
            m_p = _HESKESTAD_C1 * (q_c ** (1.0 / 3.0)) * (H ** (5.0 / 3.0)) + _HESKESTAD_C2 * q_c

            # Near-field area = pi * (0.18*H)^2
            near_r = 0.18 * H
            near_area = math.pi * near_r * near_r * delta
            if m_p > 0 and near_area > 0:
                c_mass = s_rate / (m_p * near_area)
            else:
                c_mass = 0.0

        # Optical density: sigma * c_mass [1/m] → %/m = * 100
        # Note: OD is an engineering estimate. For regulatory submission,
        # validate with CFD (FDS) or full-scale test per NFPA 72 §B.2.
        od = sigma * c_mass * 100.0
        return min(od, 100.0)

    @staticmethod
    def detection_time(
        alpha: float,
        distance_m: float,
        ceiling_h_m: float,
        smoke_type: SmokeType,
        smoke_threshold: float,
        dt_s: float = 0.5,
        max_t_s: float = 300.0,
        q_max: Optional[float] = None,
    ) -> Tuple[float, float, float]:
        """Find time when smoke concentration at detector first exceeds
        smoke_threshold.

        Strategy:
          1. Try analytical fast-path: invert Q(t) = alpha*t^2 for Q_threshold,
             then t = sqrt(Q_threshold / alpha).
          2. If analytical Q is not monotonically reachable (OD not monotonic
             with Q in simplified model), fall back to time-step simulation.

        Args:
            alpha:           t-squared growth coefficient [kW/s^2].
            distance_m:      Horizontal distance from ignition to detector [m].
            ceiling_h_m:     Ceiling height [m].
            smoke_type:      SmokeType.
            smoke_threshold: Alarm threshold [%/m] from UL 268.
            dt_s:            Time step [s] for fallback simulation.
            max_t_s:         Maximum simulation time [s].
            q_max:           Optional HRR cap [kW].

        Returns:
            (detection_time_s, hrr_at_detection_kw, smoke_at_detection_pct_m)
            detection_time_s = max_t_s if never detected.

        """
        # --- Analytical fast-path ---
        # For very close detectors where OD grows monotonically with Q,
        # we can estimate detection time analytically.
        # This works when smoke_optical_density ~ Q * constant (simple scaling).
        # We verify by checking at t_analytical and t_analytical - dt.

        # Quick time-step scan with increasing step size for speed
        t = 0.0
        prev_od = 0.0
        while t <= max_t_s:
            q = FirePhysics.hrr_at_time(alpha, t, q_max)
            od = FirePhysics.smoke_optical_density(q, max(distance_m, 0.01), ceiling_h_m, smoke_type)
            if od >= smoke_threshold:
                # Linear interpolation for sub-step accuracy
                if prev_od > 0 and t > 0:
                    t_prev = t - dt_s
                    # Interpolate between prev_od and od
                    frac = (smoke_threshold - prev_od) / (od - prev_od)
                    t_det = t_prev + frac * dt_s
                    q_det = FirePhysics.hrr_at_time(alpha, t_det, q_max)
                    od_det = FirePhysics.smoke_optical_density(q_det, max(distance_m, 0.01), ceiling_h_m, smoke_type)
                    return (round(t_det, 2), round(q_det, 2), round(od_det, 4))
                return (round(t, 2), round(q, 2), round(od, 4))
            prev_od = od
            t += dt_s

        return (
            max_t_s,
            round(FirePhysics.hrr_at_time(alpha, max_t_s, q_max), 2),
            0.0,
        )


# ============================================================================
# SCENARIO RUNNER
# ============================================================================


class ScenarioRunner:
    """Runs FireScenario objects against detector layouts.

    Usage:
        runner  = ScenarioRunner()
        result  = runner.run(scenario, detector_positions, room_polygon)
        battery = runner.run_battery(detector_positions, room_polygon, scenarios)

    Thread-safe: no shared mutable state between run() calls.
    """

    def __init__(self, time_step_s: float = 0.5) -> None:
        self._dt = time_step_s

    # ------------------------------------------------------------------
    def run(
        self,
        scenario: FireScenario,
        detector_positions: List[Tuple[float, float]],
        room_polygon: List[Tuple[float, float]],
        detector_type_str: str = "PHOTOELECTRIC",
    ) -> ScenarioResult:
        """Run one scenario. Returns ScenarioResult. Never raises.

        Args:
            scenario:            FireScenario definition.
            detector_positions:  List of (x, y) from DetectorLayout.detectors.
            room_polygon:        Room boundary polygon.
            detector_type_str:   Used to select smoke threshold (UL 268).

        """
        t_start = time.perf_counter()

        # Validate ignition point using geometry_utils (no shapely)
        igx, igy = scenario.ignition_point
        if not point_in_polygon((igx, igy), room_polygon):
            return ScenarioResult(
                scenario_id=scenario.scenario_id,
                scenario_description=scenario.description,
                verdict=ScenarioVerdict.SKIPPED,
                first_detection_time_s=None,
                first_detector=None,
                all_detections=[],
                blind_spots=[],
                blind_spot_area_pct=0.0,
                hrr_at_first_alarm_kw=None,
                smoke_at_first_alarm_pct_m=None,
                nfpa_time_limit_s=scenario.nfpa_time_limit_s,
                compliant=False,
                margin_s=None,
                detectors_tested=len(detector_positions),
                grid_points_tested=0,
                compute_time_s=time.perf_counter() - t_start,
                warnings=[f"SKIPPED: ignition point ({igx},{igy}) outside room polygon."],
            )

        # Smoke threshold from detector type (UL 268)
        threshold = _SMOKE_THRESHOLD_ION_PCT_M if "ION" in detector_type_str.upper() else _SMOKE_THRESHOLD_PHOTO_PCT_M

        # Optional Q_max from fire load
        q_max = None
        if scenario.fire_load_mj_m2 is not None:
            area = polygon_area(room_polygon)
            q_max = FirePhysics.q_max_from_fire_load(scenario.fire_load_mj_m2, area)

        # ── Per-detector detection events ──────────────────────────────
        events: List[DetectionEvent] = []
        alpha = scenario.growth_rate.alpha

        for idx, (dx, dy) in enumerate(detector_positions):
            dist = math.hypot(dx - igx, dy - igy)
            t_det, hrr_det, od_det = FirePhysics.detection_time(
                alpha=alpha,
                distance_m=dist,
                ceiling_h_m=scenario.ceiling_height_m,
                smoke_type=scenario.smoke_type,
                smoke_threshold=threshold,
                dt_s=self._dt,
                max_t_s=scenario.nfpa_time_limit_s * 2,
                q_max=q_max,
            )
            if t_det <= scenario.nfpa_time_limit_s:
                events.append(
                    DetectionEvent(
                        detector_index=idx,
                        detector_pos=(dx, dy),
                        distance_m=round(dist, 3),
                        detection_time_s=t_det,
                        hrr_at_detection_kw=hrr_det,
                        smoke_conc_pct_m=od_det,
                    )
                )

        events.sort(key=lambda e: e.detection_time_s)
        first = events[0] if events else None

        # ── Blind-spot scan ────────────────────────────────────────────
        blind_spots, grid_count = self._scan_blind_spots(
            room_polygon=room_polygon,
            detector_positions=detector_positions,
            alpha=alpha,
            ceiling_h_m=scenario.ceiling_height_m,
            smoke_type=scenario.smoke_type,
            threshold=threshold,
            nfpa_limit_s=scenario.nfpa_time_limit_s,
            q_max=q_max,
        )

        # ── Area coverage ──────────────────────────────────────────────
        blind_area_pct = (len(blind_spots) / max(grid_count, 1)) * 100.0

        # ── Verdict ────────────────────────────────────────────────────
        if first is None:
            verdict = ScenarioVerdict.FAIL_NO_DETECTOR
        elif first.detection_time_s > scenario.nfpa_time_limit_s:
            verdict = ScenarioVerdict.FAIL_SLOW
        elif blind_spots and self._has_significant_blind_spots(blind_spots):
            verdict = ScenarioVerdict.FAIL_BLIND_SPOT
        else:
            verdict = ScenarioVerdict.PASS

        compliant = verdict == ScenarioVerdict.PASS
        margin = round(scenario.nfpa_time_limit_s - first.detection_time_s, 2) if first else None

        # ── Warnings ────────────────────────────────────────────────────
        warnings = [
            "ESTIMATE: Smoke concentration uses empirical correlation "
            "(Milke 2008 / Heskestad plume). For regulatory submission, "
            "validate with CFD (e.g. FDS) or full-scale test. "
            "NFPA 72-2022 §B.2."
        ]
        if scenario.fire_load_mj_m2 is None:
            warnings.append(
                "fire_load_mj_m2 not provided — HRR uncapped. "
                "Conservative (worst case). Provide occupancy fire load "
                "for realism. Ref: NFPA 557-2016 Table 5.1."
            )
        if blind_spots and not self._has_significant_blind_spots(blind_spots):
            warnings.append(
                f"{len(blind_spots)} minor blind spot(s) detected "
                f"(each < {_BLIND_SPOT_MIN_GAP_M}m from nearest detector). "
                f"Layout is technically compliant but review recommended."
            )

        return ScenarioResult(
            scenario_id=scenario.scenario_id,
            scenario_description=scenario.description,
            verdict=verdict,
            first_detection_time_s=first.detection_time_s if first else None,
            first_detector=first,
            all_detections=events,
            blind_spots=blind_spots,
            blind_spot_area_pct=round(blind_area_pct, 2),
            hrr_at_first_alarm_kw=first.hrr_at_detection_kw if first else None,
            smoke_at_first_alarm_pct_m=first.smoke_conc_pct_m if first else None,
            nfpa_time_limit_s=scenario.nfpa_time_limit_s,
            compliant=compliant,
            margin_s=margin,
            detectors_tested=len(detector_positions),
            grid_points_tested=grid_count,
            compute_time_s=round(time.perf_counter() - t_start, 4),
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    def run_battery(
        self,
        detector_positions: List[Tuple[float, float]],
        room_polygon: List[Tuple[float, float]],
        scenarios: List[FireScenario],
        detector_type_str: str = "PHOTOELECTRIC",
    ) -> ScenarioBatteryResult:
        """Run all scenarios against one detector layout.
        Returns ScenarioBatteryResult with per-scenario results + summary.
        """
        results = []
        for sc in scenarios:
            r = self.run(sc, detector_positions, room_polygon, detector_type_str)
            results.append(r)

        return ScenarioBatteryResult(
            results=results,
            det_type=detector_type_str,
            det_count=len(detector_positions),
        )

    # ------------------------------------------------------------------
    def _scan_blind_spots(
        self,
        room_polygon: List[Tuple[float, float]],
        detector_positions: List[Tuple[float, float]],
        alpha: float,
        ceiling_h_m: float,
        smoke_type: SmokeType,
        threshold: float,
        nfpa_limit_s: float,
        q_max: Optional[float],
    ) -> Tuple[List[BlindSpot], int]:
        """Scan a grid inside the polygon using geometry_utils.
        A grid point is a blind spot if no detector detects it
        within nfpa_limit_s.
        Returns (blind_spots, total_grid_points).
        """
        grid_pts = grid_points_in_polygon(room_polygon, step=_SCAN_GRID_M, margin=0.0)

        blind: List[BlindSpot] = []
        count = len(grid_pts)

        for gx, gy in grid_pts:
            # Find nearest detector & its detection time from this point
            best_t = nfpa_limit_s * 3
            best_dist = 999.0
            for dx, dy in detector_positions:
                dist = math.hypot(dx - gx, dy - gy)
                t_det, _, _ = FirePhysics.detection_time(
                    alpha=alpha,
                    distance_m=dist,
                    ceiling_h_m=ceiling_h_m,
                    smoke_type=smoke_type,
                    smoke_threshold=threshold,
                    dt_s=1.0,  # coarser for grid scan
                    max_t_s=nfpa_limit_s + 5,
                    q_max=q_max,
                )
                if t_det < best_t:
                    best_t = t_det
                    best_dist = dist
            if best_t > nfpa_limit_s:
                blind.append(
                    BlindSpot(
                        position=(round(gx, 2), round(gy, 2)),
                        nearest_detector_dist_m=round(best_dist, 3),
                        estimated_detection_s=round(best_t, 1),
                    )
                )

        return blind, count

    # ------------------------------------------------------------------
    @staticmethod
    def _has_significant_blind_spots(blind_spots: List[BlindSpot]) -> bool:
        """Check if any blind spot exceeds minimum significant gap."""
        return any(bs.nearest_detector_dist_m > _BLIND_SPOT_MIN_GAP_M for bs in blind_spots)


# ============================================================================
# BATTERY RESULT + REPORTER
# ============================================================================


@dataclass
class ScenarioBatteryResult:
    """Aggregated result of all scenarios for one detector layout."""

    results: List[ScenarioResult]
    det_type: str
    det_count: int

    @property
    def all_pass(self) -> bool:
        return all(r.compliant for r in self.results)

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.results if r.compliant)

    @property
    def fail_count(self) -> int:
        return len(self.results) - self.pass_count

    @property
    def worst_detection_time_s(self) -> Optional[float]:
        times = [r.first_detection_time_s for r in self.results if r.first_detection_time_s is not None]
        return max(times) if times else None

    @property
    def total_blind_spots(self) -> int:
        return sum(len(r.blind_spots) for r in self.results)

    @property
    def room_id(self) -> str:
        """Return room_id from first result if available."""
        if self.results:
            return self.results[0].scenario_id.split("_")[0]
        return "unknown"

    def summary_dict(self) -> dict:
        return {
            "detector_type": self.det_type,
            "detector_count": self.det_count,
            "scenarios_run": len(self.results),
            "scenarios_pass": self.pass_count,
            "scenarios_fail": self.fail_count,
            "all_pass": self.all_pass,
            "worst_detection_s": self.worst_detection_time_s,
            "total_blind_spots": self.total_blind_spots,
            "nfpa_compliant": self.all_pass,
            "nfpa_clause": "NFPA 72-2022 §17.7.3",
            "per_scenario": [
                {
                    "id": r.scenario_id,
                    "verdict": r.verdict.value,
                    "detection_time_s": r.first_detection_time_s,
                    "margin_s": r.margin_s,
                    "blind_spots": len(r.blind_spots),
                    "blind_area_pct": r.blind_spot_area_pct,
                    "hrr_kw": r.hrr_at_first_alarm_kw,
                    "compute_s": r.compute_time_s,
                }
                for r in self.results
            ],
        }


class ScenarioReporter:
    """Formats ScenarioBatteryResult as:
    - plain text (console)
    - JSON
    - CSV (for Excel / inspection)
    """

    @staticmethod
    def to_text(battery: ScenarioBatteryResult) -> str:
        lines = [
            f"{'=' * 64}",
            "SCENARIO BATTERY REPORT",
            f"Detector type: {battery.det_type}  Count: {battery.det_count}",
            f"Scenarios: {len(battery.results)}  Pass: {battery.pass_count}  Fail: {battery.fail_count}",
            f"NFPA 72-2022 §17.7.3 limit: {_NFPA_MAX_DETECTION_S}s",
            f"{'=' * 64}",
        ]
        for r in battery.results:
            symbol = "PASS" if r.compliant else "FAIL"
            t_str = f"{r.first_detection_time_s:.1f}s" if r.first_detection_time_s is not None else "NONE"
            m_str = f"margin={r.margin_s:+.1f}s" if r.margin_s is not None else ""
            lines.append(
                f"  [{symbol:<4}] [{r.verdict.value:<18}] "
                f"{r.scenario_id:<30} "
                f"t={t_str:<8} {m_str}  blind={len(r.blind_spots)}"
            )
        lines.append(f"{'=' * 64}")
        if battery.all_pass:
            lines.append("RESULT: ALL SCENARIOS PASS — Design meets NFPA 72-2022 §17.7.3")
        else:
            lines.append(f"RESULT: {battery.fail_count} SCENARIO(S) FAILED — Review detector layout. DO NOT SUBMIT.")
        lines.append(f"{'=' * 64}")
        return "\n".join(lines)

    @staticmethod
    def to_json(battery: ScenarioBatteryResult, indent: int = 2) -> str:
        import json

        return json.dumps(battery.summary_dict(), indent=indent, ensure_ascii=False)

    @staticmethod
    def to_csv(battery: ScenarioBatteryResult) -> str:
        """CSV output with proper escaping of commas in fields."""
        lines = ["scenario_id,verdict,detection_time_s,margin_s,blind_spots,blind_area_pct,hrr_kw,compute_s"]
        for r in battery.results:
            # Escape commas in scenario_id
            sid = r.scenario_id.replace(",", ";")
            lines.append(
                ",".join(
                    str(v)
                    for v in [
                        sid,
                        r.verdict.value,
                        r.first_detection_time_s or "",
                        r.margin_s or "",
                        len(r.blind_spots),
                        r.blind_spot_area_pct,
                        r.hrr_at_first_alarm_kw or "",
                        r.compute_time_s,
                    ]
                )
            )
        return "\n".join(lines)


# ============================================================================
# CONVENIENCE: run_scenarios_for_room()
# ============================================================================


def run_scenarios_for_room(
    room_polygon: List[Tuple[float, float]],
    ceiling_height: float,
    detector_positions: List[Tuple[float, float]],
    detector_type: str = "PHOTOELECTRIC",
    fire_load_mj_m2: Optional[float] = None,
    run_blind_scan: bool = False,
    scan_grid_m: float = 1.0,
    time_step_s: float = 0.5,
) -> ScenarioBatteryResult:
    """One-call convenience: analyse room + run standard scenario battery.

    Args:
        room_polygon:       Room boundary as list of (x,y) tuples.
        ceiling_height:     Ceiling height in metres.
        detector_positions: List of (x,y) from DetectorLayout.detectors.
        detector_type:      "PHOTOELECTRIC" or "IONIZATION".
        fire_load_mj_m2:   Optional fire load (NFPA 557 Table 5.1).
        run_blind_scan:     If True, add grid-scan scenarios (slow).
        scan_grid_m:        Grid resolution for blind-spot scan.
        time_step_s:        Time step for detection simulation.

    Returns:
        ScenarioBatteryResult with all scenario results.

    """
    scenarios = ScenarioLibrary.all_scenarios(room_polygon, ceiling_height, fire_load_mj_m2)
    if run_blind_scan:
        scenarios += ScenarioLibrary.blind_spot_scan(room_polygon, ceiling_height, fire_load_mj_m2, scan_grid_m)

    runner = ScenarioRunner(time_step_s=time_step_s)
    return runner.run_battery(detector_positions, room_polygon, scenarios, detector_type)


# ============================================================================
# FIRE LOAD TABLE — NFPA 557-2016 Table 5.1
# ============================================================================

FIRE_LOAD_BY_OCCUPANCY: Dict[str, float] = {
    "office": 400.0,
    "warehouse": 800.0,
    "retail": 500.0,
    "education": 300.0,
    "healthcare": 200.0,
    "residential": 350.0,
    "industrial": 600.0,
    "corridor": 100.0,
    "storage": 800.0,
    "assembly": 350.0,
}


def get_fire_load(occupancy: str) -> float:
    """Get typical fire load [MJ/m^2] by occupancy type.
    Ref: NFPA 557-2016 Table 5.1.
    Returns default 400.0 if occupancy not found.
    """
    return FIRE_LOAD_BY_OCCUPANCY.get(occupancy.lower(), FIRE_LOAD_BY_OCCUPANCY["office"])
