"""
conveyor_fire.py — Conveyor belt fire analysis per NFPA 120 §8.4.

V214: Implements conveyor belt fire protection calculations per:
  - NFPA 120-2022 §8.4 (Conveyor Belt Fire Protection)
  - MSHA 30 CFR §75.1108 (Fire Protection for Conveyor Belts)
  - MSHA 30 CFR §75.1108-1 (Slideshow: Belt Fire Suppression Requirements)

REQUIREMENTS (NFPA 120 §8.4):
  1. All conveyor belts must be fire-resistant (MSHA 30 CFR §75.1108)
  2. Automatic fire suppression system required at:
     - Drive heads
     - Tail pieces
     - Take-up storage units
     - Every 300m (1000ft) along the belt
  3. CO monitoring required at belt entries (MSHA §75.351)
  4. Belt air (ventilation air for belt entries) must be monitored

CO THRESHOLDS (MSHA 30 CFR §75.351):
  - 10 ppm  → Alert level, notify foreman
  - 15 ppm  → Evacuate personnel from belt entry
  - 30 ppm  → Withdraw all personnel, activate suppression
  - 50 ppm  → Imminent danger, full mine evacuation
"""

from __future__ import annotations

from dataclasses import dataclass

# CO thresholds (MSHA 30 CFR §75.351)
CO_ALERT_PPM = 10.0
CO_EVACUATE_PPM = 15.0
CO_WITHDRAW_PPM = 30.0
CO_IMMINENT_PPM = 50.0

# Suppression system spacing (NFPA 120 §8.4.3)
SUPPRESSION_MAX_SPACING_M = 300.0  # 1000 ft

# Minimum water flow for suppression (NFPA 120 §8.4.5)
MIN_WATER_FLOW_LPM_PER_M2 = 10.0  # 10 L/min per m² of belt area
MIN_WATER_DURATION_MIN = 10.0  # 10 minutes minimum


@dataclass
class ConveyorSpec:
    """Conveyor belt specifications."""
    belt_length_m: float
    belt_width_m: float
    belt_speed_m_s: float
    has_fire_resistant_belt: bool = True
    number_of_drives: int = 1
    number_of_tail_pieces: int = 1
    has_take_up: bool = True


@dataclass
class SuppressionSystemDesign:
    """Design for conveyor belt fire suppression system."""
    number_of_nozzle_groups: int
    water_flow_rate_lpm: float
    water_duration_min: float
    total_water_volume_l: float
    nozzle_locations: list[str]
    is_compliant: bool
    violations: list[str]

    def __post_init__(self):
        if self.nozzle_locations is None:
            self.nozzle_locations = []
        if self.violations is None:
            self.violations = []


class ConveyorFireAnalyzer:
    """
    Conveyor belt fire protection analysis per NFPA 120 §8.4 + MSHA.
    """

    @staticmethod
    def classify_co_hazard(co_concentration_ppm: float) -> str:
        """
        Classify CO concentration per MSHA thresholds.

        Args:
            co_concentration_ppm: CO in parts per million.

        Returns:
            One of: 'normal', 'alert', 'evacuate', 'withdraw', 'imminent'.
        """
        if co_concentration_ppm < CO_ALERT_PPM:
            return "normal"
        elif co_concentration_ppm < CO_EVACUATE_PPM:
            return "alert"
        elif co_concentration_ppm < CO_WITHDRAW_PPM:
            return "evacuate"
        elif co_concentration_ppm < CO_IMMINENT_PPM:
            return "withdraw"
        else:
            return "imminent"

    @staticmethod
    def design_suppression_system(spec: ConveyorSpec) -> SuppressionSystemDesign:
        """
        Design a fire suppression system for a conveyor belt.

        Per NFPA 120 §8.4.3, suppression is required at:
          - Each drive head
          - Each tail piece
          - Take-up storage unit (if present)
          - Every 300m along the belt

        Args:
            spec: ConveyorSpec with belt dimensions + configuration.

        Returns:
            SuppressionSystemDesign with nozzle count, water flow, etc.
        """
        violations = []
        nozzle_locations = []

        # Drive heads
        for i in range(spec.number_of_drives):
            nozzle_locations.append(f"Drive {i+1}")
        # Tail pieces
        for i in range(spec.number_of_tail_pieces):
            nozzle_locations.append(f"Tail {i+1}")
        # Take-up
        if spec.has_take_up:
            nozzle_locations.append("Take-up")

        # Intermediate suppression every 300m
        if spec.belt_length_m > SUPPRESSION_MAX_SPACING_M:
            num_intermediate = int(spec.belt_length_m / SUPPRESSION_MAX_SPACING_M)
            for i in range(num_intermediate):
                nozzle_locations.append(f"Intermediate {i+1} ({(i+1)*300}m)")

        total_groups = len(nozzle_locations)

        # Water flow calculation
        # Each group covers ~300m of belt (or full length if shorter)
        coverage_per_group_m = min(SUPPRESSION_MAX_SPACING_M, spec.belt_length_m)
        coverage_area_per_group_m2 = coverage_per_group_m * spec.belt_width_m
        water_flow_per_group_lpm = coverage_area_per_group_m2 * MIN_WATER_FLOW_LPM_PER_M2
        total_water_flow_lpm = water_flow_per_group_lpm * total_groups

        # Water volume = flow × duration
        total_water_volume_l = total_water_flow_lpm * MIN_WATER_DURATION_MIN

        # Compliance checks
        if not spec.has_fire_resistant_belt:
            violations.append(
                "CONVEYOR BELT is NOT fire-resistant — violates MSHA 30 CFR "
                "§75.1108. All underground conveyor belts must be fire-resistant."
            )

        if total_groups == 0:
            violations.append("No suppression nozzle groups designed — belt length too short.")

        return SuppressionSystemDesign(
            number_of_nozzle_groups=total_groups,
            water_flow_rate_lpm=round(total_water_flow_lpm, 1),
            water_duration_min=MIN_WATER_DURATION_MIN,
            total_water_volume_l=round(total_water_volume_l, 1),
            nozzle_locations=nozzle_locations,
            is_compliant=len(violations) == 0,
            violations=violations,
        )

    @staticmethod
    def estimate_fire_spread_rate(
        belt_speed_m_s: float,
        belt_material: str = "fire_resistant",
    ) -> float:
        """
        Estimate fire spread rate along a conveyor belt.

        Fire spread rate depends on:
          - Belt speed (faster belt = faster spread)
          - Belt material (fire-resistant vs standard)
          - Airflow direction (not modeled here)

        Per MSHA research (NIOSH RI 9670):
          - Fire-resistant belt: ~0.05 m/s spread rate
          - Standard belt: ~0.15 m/s spread rate
          - Belt speed adds to spread rate (50% of belt speed)

        Args:
            belt_speed_m_s: Conveyor belt speed in m/s.
            belt_material: 'fire_resistant' or 'standard'.

        Returns:
            Estimated fire spread rate in m/s.
        """
        base_rate = 0.05 if belt_material == "fire_resistant" else 0.15
        belt_contribution = belt_speed_m_s * 0.5
        return round(base_rate + belt_contribution, 3)
