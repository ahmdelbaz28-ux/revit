"""
ventilation_calculator.py — Mine ventilation calculations per Atkinson equation.

V214: Implements ventilation calculations per:
  - NFPA 120-2022 §7.2 (Ventilation)
  - MSHA 30 CFR §75.300-399 (Ventilation)
  - Atkinson's equation: ΔP = R × Q²

ATKINSON EQUATION:
  ΔP = R × Q² × ρ / ρ₀

  where:
    ΔP = pressure drop (Pa)
    R  = resistance (N·s²/m⁸)
    Q  = airflow (m³/s)
    ρ  = air density (kg/m³)
    ρ₀ = standard air density (1.2 kg/m³)

MINIMUM AIRFLOW REQUIREMENTS (MSHA):
  - Last open crosscut: 9,000 CFM (4.25 m³/s) minimum
  - Working face: 3,000 CFM (1.42 m³/s) minimum
  - Belt entry: 500 CFM (0.24 m³/s) per foot of belt width
"""

from __future__ import annotations

from dataclasses import dataclass

# Standard air density (MSHA reference)
STANDARD_AIR_DENSITY_KG_M3 = 1.2

# MSHA minimum airflow requirements (30 CFR §75)
MIN_AIRFLOW_LAST_OPEN_CROSSCUT_M3_S = 4.25  # 9,000 CFM
MIN_AIRFLOW_WORKING_FACE_M3_S = 1.42  # 3,000 CFM
MIN_AIRFLOW_BELT_ENTRY_M3_S_PER_M = 0.78  # 500 CFM per foot → converted per meter

# Methane dilution airflow (to keep CH4 below 1%)
# Per MSHA: minimum 0.06 m³/s per ton of coal mined per day
METHANE_DILUTION_M3_S_PER_TON_DAY = 0.06


@dataclass
class VentilationResult:
    """Result of ventilation calculation."""
    airflow_m3_s: float
    pressure_drop_pa: float
    resistance_n_s2_m8: float
    air_velocity_m_s: float | None = None
    is_compliant: bool = False
    violations: list[str] = None

    def __post_init__(self):
        if self.violations is None:
            self.violations = []


class VentilationCalculator:
    """
    Mine ventilation calculations per Atkinson equation + MSHA requirements.
    """

    @staticmethod
    def pressure_drop(
        resistance: float,
        airflow_m3_s: float,
        air_density_kg_m3: float = STANDARD_AIR_DENSITY_KG_M3,
    ) -> float:
        """
        Calculate pressure drop using Atkinson's equation.

        ΔP = R × Q² × (ρ / ρ₀)

        Args:
            resistance: Airway resistance in N·s²/m⁸
            airflow_m3_s: Airflow in m³/s
            air_density_kg_m3: Actual air density (default 1.2 kg/m³)

        Returns:
            Pressure drop in Pascals (Pa).
        """
        if resistance < 0:
            raise ValueError("Resistance must be >= 0")
        if airflow_m3_s < 0:
            raise ValueError("Airflow must be >= 0")
        density_ratio = air_density_kg_m3 / STANDARD_AIR_DENSITY_KG_M3
        return resistance * (airflow_m3_s ** 2) * density_ratio

    @staticmethod
    def airway_resistance(
        length_m: float,
        perimeter_m: float,
        area_m2: float,
        friction_factor: float = 0.01,
    ) -> float:
        """
        Calculate airway resistance from geometry.

        R = (K × L × P) / A³

        where:
          K = friction factor (N·s²/m⁴, typical 0.01 for smooth concrete)
          L = length (m)
          P = perimeter (m)
          A = cross-sectional area (m²)

        Args:
            length_m: Airway length in meters
            perimeter_m: Airway perimeter in meters
            area_m2: Cross-sectional area in m²
            friction_factor: K value (default 0.01 for smooth)

        Returns:
            Resistance in N·s²/m⁸.
        """
        if area_m2 <= 0:
            raise ValueError("Area must be > 0")
        if length_m < 0 or perimeter_m < 0:
            raise ValueError("Length and perimeter must be >= 0")
        return (friction_factor * length_m * perimeter_m) / (area_m2 ** 3)

    @staticmethod
    def air_velocity(airflow_m3_s: float, area_m2: float) -> float:
        """Calculate air velocity: V = Q / A."""
        if area_m2 <= 0:
            raise ValueError("Area must be > 0")
        return airflow_m3_s / area_m2

    @staticmethod
    def check_msha_compliance(
        airflow_m3_s: float,
        location_type: str = "working_face",
        cross_sectional_area_m2: float | None = None,
    ) -> tuple[bool, list[str]]:
        """
        Check if airflow meets MSHA minimum requirements.

        Args:
            airflow_m3_s: Actual airflow in m³/s
            location_type: 'working_face', 'last_open_crosscut', or 'belt_entry'
            cross_sectional_area_m2: For velocity check (MSHA max 3.05 m/s)

        Returns:
            Tuple of (is_compliant, list_of_violations).
        """
        violations = []

        if location_type == "working_face":
            if airflow_m3_s < MIN_AIRFLOW_WORKING_FACE_M3_S:
                violations.append(
                    f"Working face airflow {airflow_m3_s:.2f} m³/s below MSHA "
                    f"minimum of {MIN_AIRFLOW_WORKING_FACE_M3_S} m³/s "
                    f"(30 CFR §75.326)"
                )
        elif location_type == "last_open_crosscut":
            if airflow_m3_s < MIN_AIRFLOW_LAST_OPEN_CROSSCUT_M3_S:
                violations.append(
                    f"Last open crosscut airflow {airflow_m3_s:.2f} m³/s below "
                    f"MSHA minimum of {MIN_AIRFLOW_LAST_OPEN_CROSSCUT_M3_S} m³/s "
                    f"(30 CFR §75.327)"
                )
        elif location_type == "belt_entry":
            # Belt entry: 0.78 m³/s per meter of belt width
            # Assuming standard 1.07m (42") belt → 0.83 m³/s minimum
            min_belt = MIN_AIRFLOW_BELT_ENTRY_M3_S_PER_M * 1.07
            if airflow_m3_s < min_belt:
                violations.append(
                    f"Belt entry airflow {airflow_m3_s:.2f} m³/s below MSHA "
                    f"minimum of {min_belt:.2f} m³/s (30 CFR §75.350)"
                )

        # Check velocity (MSHA: max 3.05 m/s to prevent dust entrainment)
        if cross_sectional_area_m2 and cross_sectional_area_m2 > 0:
            velocity = airflow_m3_s / cross_sectional_area_m2
            if velocity > 3.05:
                violations.append(
                    f"Air velocity {velocity:.2f} m/s exceeds MSHA maximum of "
                    f"3.05 m/s (dust entrainment risk, 30 CFR §75.326)"
                )

        return (len(violations) == 0, violations)

    @staticmethod
    def methane_dilution_airflow(
        methane_emission_m3_s: float,
        target_max_pct: float = 1.0,
    ) -> float:
        """
        Calculate minimum airflow to dilute methane below target %.

        Q = (CH4_emission / target_pct) × 100

        Per MSHA, target should be ≤ 1.0% (well below LEL of 5%).

        Args:
            methane_emission_m3_s: Methane emission rate in m³/s
            target_max_pct: Maximum allowable CH4 % (default 1.0)

        Returns:
            Minimum airflow in m³/s.
        """
        if target_max_pct <= 0:
            raise ValueError("Target must be > 0")
        if methane_emission_m3_s <= 0:
            return 0.0
        return (methane_emission_m3_s / target_max_pct) * 100
