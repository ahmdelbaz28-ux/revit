"""
methane_calculator.py — Methane layering + LEL/UEL calculations for mines.

V214: Implements methane gas calculations per:
  - NFPA 120-2022 §7.3 (Methane Monitoring)
  - MSHA 30 CFR §75.323 (Methane Tests)
  - IEC 60079-10-1:2015 (Area Classification for methane)

METHANE PROPERTIES (CH4):
  - LEL (Lower Explosive Limit): 5.0% by volume in air
  - UEL (Upper Explosive Limit): 15.0% by volume in air
  - Density: 0.657 kg/m³ at 20°C (lighter than air → layering at roof)
  - Molecular weight: 16.04 g/mol

SAFETY THRESHOLDS (MSHA 30 CFR §75.323):
  - 0.25% → Normal background, continue operations
  - 0.5%  → Notify mine foreman, increase ventilation
  - 1.0%  → Remove personnel from affected area
  - 1.5%  → De-energize electrical equipment
  - 2.0%  → Withdraw all personnel, post warning signs
  - 5.0%  → Explosive atmosphere — evacuate immediately
"""

from __future__ import annotations

from dataclasses import dataclass

# Methane physical constants
CH4_LEL_PCT = 5.0  # % by volume in air
CH4_UEL_PCT = 15.0
CH4_DENSITY_KG_M3 = 0.657  # at 20°C, 1 atm
CH4_MOLAR_MASS_G_MOL = 16.04
AIR_DENSITY_KG_M3 = 1.225  # at 15°C, 1 atm

# MSHA action levels (30 CFR §75.323)
MSHA_THRESHOLDS = {
    "normal": 0.25,        # % — continue operations
    "notify": 0.5,         # % — notify foreman, increase ventilation
    "evacuate_area": 1.0,  # % — remove personnel from area
    "deenergize": 1.5,     # % — de-energize electrical equipment
    "withdraw_all": 2.0,   # % — withdraw all personnel
    "explosive": 5.0,      # % — explosive atmosphere
}


@dataclass
class MethaneReading:
    """A single methane concentration reading."""
    concentration_pct: float  # % by volume in air
    location: str = ""
    timestamp: str = ""
    sensor_id: str = ""


@dataclass
class MethaneLayeringResult:
    """Result of methane layering analysis."""
    roof_concentration_pct: float
    mid_concentration_pct: float
    floor_concentration_pct: float
    layering_index: float  # >1.0 indicates significant layering
    is_stratified: bool
    action_required: str


class MethaneCalculator:
    """
    Methane gas calculations for underground mining.

    Per NFPA 120-2022 + MSHA 30 CFR Part 75.
    """

    @staticmethod
    def classify_hazard(concentration_pct: float) -> str:
        """
        Classify methane concentration per MSHA thresholds.

        Args:
            concentration_pct: CH4 concentration in % by volume.

        Returns:
            One of: 'normal', 'notify', 'evacuate_area', 'deenergize',
            'withdraw_all', 'explosive'.
        """
        if concentration_pct < MSHA_THRESHOLDS["notify"]:
            return "normal"
        elif concentration_pct < MSHA_THRESHOLDS["evacuate_area"]:
            return "notify"
        elif concentration_pct < MSHA_THRESHOLDS["deenergize"]:
            return "evacuate_area"
        elif concentration_pct < MSHA_THRESHOLDS["withdraw_all"]:
            return "deenergize"
        elif concentration_pct < MSHA_THRESHOLDS["explosive"]:
            return "withdraw_all"
        else:
            return "explosive"

    @staticmethod
    def is_in_explosive_range(concentration_pct: float) -> bool:
        """Check if concentration is within explosive range (LEL ≤ c ≤ UEL)."""
        return CH4_LEL_PCT <= concentration_pct <= CH4_UEL_PCT

    @staticmethod
    def distance_to_lel(concentration_pct: float) -> float:
        """
        Calculate how far the concentration is from LEL (5%).

        Returns:
            Negative if below LEL (safe margin), positive if above.
            0.0 means at LEL exactly.
        """
        return concentration_pct - CH4_LEL_PCT

    @staticmethod
    def analyze_layering(
        roof_pct: float,
        mid_pct: float,
        floor_pct: float,
    ) -> MethaneLayeringResult:
        """
        Analyze methane layering in a mine opening.

        Methane is lighter than air (0.657 vs 1.225 kg/m³) and accumulates
        at the roof. NFPA 120 §7.3 requires monitoring at multiple heights.

        The layering index = roof_concentration / average_concentration.
        A value > 1.5 indicates significant stratification that requires
        increased ventilation.

        Args:
            roof_pct: Methane % at roof (top of opening)
            mid_pct: Methane % at mid-height
            floor_pct: Methane % at floor (bottom of opening)

        Returns:
            MethaneLayeringResult with action recommendation.
        """
        avg = (roof_pct + mid_pct + floor_pct) / 3.0
        layering_index = roof_pct / avg if avg > 0 else 1.0
        is_stratified = layering_index > 1.5

        # Action based on roof concentration (worst case)
        action = MethaneCalculator.classify_hazard(roof_pct)
        if is_stratified and action == "normal":
            action = "notify"  # Layering itself requires notification

        return MethaneLayeringResult(
            roof_concentration_pct=roof_pct,
            mid_concentration_pct=mid_pct,
            floor_concentration_pct=floor_pct,
            layering_index=round(layering_index, 3),
            is_stratified=is_stratified,
            action_required=action,
        )

    @staticmethod
    def dilution_airflow_required(
        current_concentration_pct: float,
        target_concentration_pct: float,
        current_airflow_m3_s: float,
    ) -> float:
        """
        Calculate the airflow needed to dilute methane to a target concentration.

        Uses the dilution equation:
            Q_required = Q_current × (C_current / C_target)

        Per MSHA, the target should be ≤ 1.0% (well below LEL of 5%).

        Args:
            current_concentration_pct: Current CH4 %
            target_concentration_pct: Desired CH4 % (must be < current)
            current_airflow_m3_s: Current ventilation airflow in m³/s

        Returns:
            Required airflow in m³/s.
        """
        if target_concentration_pct <= 0:
            raise ValueError("Target concentration must be > 0")
        if current_concentration_pct <= 0:
            return 0.0  # No methane to dilute
        if target_concentration_pct >= current_concentration_pct:
            return current_airflow_m3_s  # Already at or below target

        return current_airflow_m3_s * (current_concentration_pct / target_concentration_pct)

    @staticmethod
    def time_to_lel(
        current_concentration_pct: float,
        emission_rate_m3_s: float,
        volume_m3: float,
    ) -> float:
        """
        Estimate time to reach LEL (5%) at current emission rate.

        Uses: t = (LEL% - current%) × volume / (emission_rate × 100)

        Args:
            current_concentration_pct: Current CH4 %
            emission_rate_m3_s: Methane emission rate in m³/s
            volume_m3: Volume of the opening in m³

        Returns:
            Time in seconds to reach LEL. Returns float('inf') if
            concentration is already at or above LEL.
        """
        if current_concentration_pct >= CH4_LEL_PCT:
            return 0.0
        if emission_rate_m3_s <= 0:
            return float("inf")

        delta_pct = CH4_LEL_PCT - current_concentration_pct
        delta_volume_m3 = (delta_pct / 100.0) * volume_m3
        return delta_volume_m3 / emission_rate_m3_s
