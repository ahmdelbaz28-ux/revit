"""v17_core/battery_calculator.py — NFPA 72 §10.6.7 Battery Aging & Temperature Derating
======================================================================================
CRITICAL LIFE-SAFETY MODULE — Part of the V17 Critical Trilogy

Wrapper around the physics-correct BatteryAuditor from
fireai.core.battery_aging_derating, adding DecisionProvenance audit trails
and the StrictBatterySizer class interface requested by the consultant.

The consultant's proposed code had these errors (all fixed in fireai.core):
  1. Simple 25% aging factor without IEEE 1188 end-of-life threshold
  2. Linear temperature derating (1.5% per degree) — should use IEEE 485
     temperature derating table with non-linear behavior
  3. No Peukert discharge rate correction — alarm load discharges faster
     than the 20h rate, reducing effective capacity
  4. No end-of-discharge voltage check — battery voltage can drop below
     panel minimum operating voltage
  5. Wrong import: fireai.v8_core.decision_provenance

Real-world failure scenario: A battery that passes at 25°C on day 1
will FAIL at 0°C in year 4. The consultant's code would miss this
because it used a flat 25% factor instead of the compound effect of
temperature (0.72 at 0°C) × aging (0.80 EOL) × discharge rate (0.90).

NFPA 72 References:
  - §10.6.7.2.1: Secondary supply shall have capacity for 24h standby
  - §10.6.7.1.1: Storage batteries shall be maintained fully charged
  - §10.6.7.2.2: Capacity calculations shall include all connected loads

IEEE References:
  - IEEE 485: Recommended Practice for Sizing Lead-Acid Batteries
  - IEEE 1188: VRLA Battery Maintenance, Testing, and Replacement

Usage:
    from fireai.v17_core import StrictBatterySizer

    sizer = StrictBatterySizer(standby_hours=24.0, alarm_minutes=5.0)
    provenance = sizer.calculate_minimum_ah(
        quiescent_ma=500.0,
        alarm_ma=2000.0,
        panel_ambient_temp_c=20.0,
    )
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# Import the correct provenance shim (not the consultant's fireai.v8_core path)
try:
    from fireai.core.provenance import (
        ConfidenceLevel,
        ConfidenceScore,
        DecisionProvenance,
        RuleApplied,
        Violation,
    )
except ImportError:
    DecisionProvenance = None  # type: ignore[misc,assignment]
    RuleApplied = None  # type: ignore[misc,assignment]
    Violation = None  # type: ignore[misc,assignment]
    ConfidenceScore = None  # type: ignore[misc,assignment]
    ConfidenceLevel = None  # type: ignore[misc,assignment]

# Import the physics-correct implementation from fireai.core
from fireai.core.battery_aging_derating import (
    AGING_DERATING_EOL,
    DEFAULT_SERVICE_LIFE_YEARS,
    BatterySizingResult,
    BatterySpec,
    size_battery,
)


class StrictBatterySizer:
    """V17 Strict Battery Sizer with DecisionProvenance audit trail.

    Calculates battery capacity per NFPA 72 §10.6.7 with:
      - IEEE 485 temperature derating (non-linear, not flat 1.5%/°C)
      - IEEE 1188 aging derating (80% EOL threshold)
      - Peukert discharge rate correction (VRLA n=1.20)
      - End-of-discharge voltage check

    The consultant's interface accepted mA inputs (quiescent_ma, alarm_ma)
    and used a flat 25% aging factor + linear 1.5%/°C temperature derating.
    This implementation keeps the mA interface but delegates to the correct
    physics-based calculation.

    CRITICAL: The calculation designs for the WORST CASE — end of battery
    life (80% capacity) at minimum temperature. A battery that is "adequate"
    on day 1 at 25°C may be INADEQUATE in year 4 at 0°C.

    Usage::

        from fireai.v17_core import StrictBatterySizer

        sizer = StrictBatterySizer(standby_hours=24.0, alarm_minutes=5.0)
        result = sizer.calculate_minimum_ah(
            quiescent_ma=500.0,
            alarm_ma=2000.0,
            panel_ambient_temp_c=20.0,
        )
    """

    def __init__(
        self,
        standby_hours: float = 24.0,
        alarm_minutes: float = 5.0,
        service_life_years: float = DEFAULT_SERVICE_LIFE_YEARS,
        safety_margin_pct: float = 0.0,
    ) -> None:
        """Initialize the battery sizer.

        Args:
            standby_hours: Required standby duration per NFPA 72 §10.6.7.2.1.
                Typically 24h (local) or 60h (central station).
            alarm_minutes: Required alarm duration after standby.
                Typically 5 min (local) or 15 min (central station).
            service_life_years: Expected battery service life (years).
                Default: 5 years (VRLA in fire alarm applications).
            safety_margin_pct: Additional safety margin percentage.
                IEEE 485 recommends 10-25% for critical applications.

        """
        self.req_standby_h = standby_hours
        self.req_alarm_h = alarm_minutes / 60.0
        self.service_life_years = service_life_years
        self.safety_margin_pct = safety_margin_pct

    def calculate_minimum_ah(
        self,
        quiescent_ma: float,
        alarm_ma: float,
        panel_ambient_temp_c: float = 25.0,
        installed_battery_ah: Optional[float] = None,
        battery_cells: int = 6,
    ) -> Any:
        """Calculate minimum required battery capacity with full derating.

        Converts the consultant's mA interface to the core module's A interface,
        then delegates to the physics-correct size_battery() function.

        The calculation follows this sequence:
          1. Convert mA to A
          2. Calculate Ah for standby period
          3. Calculate Ah for alarm period
          4. Apply IEEE 485 temperature derating (non-linear table)
          5. Apply IEEE 1188 aging derating (80% EOL threshold)
          6. Apply Peukert discharge rate correction (n=1.20 for VRLA)
          7. Add safety margin if specified
          8. Compare with installed battery if specified

        Args:
            quiescent_ma: Total quiescent/standby current draw in mA.
            alarm_ma: Total alarm current draw in mA.
            panel_ambient_temp_c: Expected minimum ambient temperature in °C.
                Default: 25°C (indoor conditioned space).
                For unconditioned spaces, use 0°C or lower.
            installed_battery_ah: If provided, checks adequacy of this
                battery. If None, only calculates required capacity.
            battery_cells: Number of 2V cells in series. Default: 6 (12V).

        Returns:
            DecisionProvenance with battery sizing result and audit trail,
            or dict if provenance is unavailable.

        """
        # Convert mA to A (consultant's interface uses mA)
        quiescent_a = quiescent_ma / 1000.0
        alarm_a = alarm_ma / 1000.0

        # Create battery spec if installed capacity provided
        battery = None
        if installed_battery_ah is not None and installed_battery_ah > 0:
            battery = BatterySpec(
                amp_hour_20h=installed_battery_ah,
                cells=battery_cells,
            )

        # Delegate to the physics-correct calculation
        result: BatterySizingResult = size_battery(
            standby_load_amps=quiescent_a,
            alarm_load_amps=alarm_a,
            standby_hours=self.req_standby_h,
            alarm_hours=self.req_alarm_h,
            battery=battery,
            min_temperature_c=panel_ambient_temp_c,
            service_life_years=self.service_life_years,
            safety_margin_pct=self.safety_margin_pct,
        )

        # Build DecisionProvenance if available
        if DecisionProvenance is not None:
            violations = []
            for v in result.violations:
                violations.append(
                    Violation(
                        severity=v.get("severity", "WARNING"),
                        citation="NFPA 72-2022 §10.6.7",
                        description=v.get("message", str(v)),
                    )
                )

            rules = [
                RuleApplied(
                    citation="NFPA 72-2022 §10.6.7",
                    constant_id="BATT_AGING",
                    value_used=AGING_DERATING_EOL,  # 0.80 EOL
                    unit="Multiplier",
                ),
                RuleApplied(
                    citation="NFPA 72-2022 §10.6.7.2.1",
                    constant_id="STANDBY",
                    value_used=self.req_standby_h,
                    unit="Hours",
                ),
                RuleApplied(
                    citation="IEEE 485",
                    constant_id="TEMP_DERATING",
                    value_used=result.temperature_derating,
                    unit="Multiplier",
                ),
                RuleApplied(
                    citation="IEEE 1188",
                    constant_id="EOL_THRESHOLD",
                    value_used=0.80,
                    unit="Fraction",
                ),
            ]

            has_violations = len(result.violations) > 0
            conf_level = ConfidenceLevel.LOW if has_violations else ConfidenceLevel.HIGH
            conf = ConfidenceScore(
                input_quality_score=0.95,
                rule_coverage=1.0,
                geometry_certainty=1.0,
                overall=conf_level,
            )

            value_dict: Dict[str, Any] = {
                "min_required_ah": result.required_ah,
                "base_ah": result.total_load_ah,
                "thermal_derate": result.temperature_derating,
                "aging_derate": result.aging_derating,
                "discharge_rate_correction": result.discharge_rate_correction,
            }
            if installed_battery_ah is not None:
                value_dict["installed_ah"] = result.installed_ah
                value_dict["usable_ah"] = result.usable_ah
                value_dict["is_adequate"] = result.is_adequate
                value_dict["margin_pct"] = result.margin_pct

            return DecisionProvenance.new(
                decision_type="psu_battery_sizing",
                value=value_dict,
                inputs={
                    "q_ma": quiescent_ma,
                    "a_ma": alarm_ma,
                    "temp_c": panel_ambient_temp_c,
                    "standby_h": self.req_standby_h,
                    "alarm_h": self.req_alarm_h,
                    "service_life_y": self.service_life_years,
                },
                rules_applied=rules,
                algorithm={
                    "name": "ThermalDeratedSLA",
                    "version": "v17",
                    "corrections": [
                        "IEEE 485 temperature derating table (not linear 1.5%/°C)",
                        "IEEE 1188 aging EOL threshold (not flat 25%)",
                        "Peukert discharge rate correction (n=1.20 VRLA)",
                        "End-of-discharge voltage check",
                    ],
                },
                confidence=conf,
                selected_because=(
                    f"Includes mandatory {AGING_DERATING_EOL * 100:.0f}% EOL safety gap "
                    f"against impedance degradation, IEEE 485 temperature derating, "
                    f"and Peukert discharge rate correction."
                ),
                violations=violations,
            )

        # Fallback: return result dict if provenance unavailable
        return {
            "min_required_ah": result.required_ah,
            "base_ah": result.total_load_ah,
            "thermal_derate": result.temperature_derating,
            "aging_derate": result.aging_derating,
            "is_adequate": result.is_adequate,
            "violations": result.violations,
            "details": result.details,
        }

    def audit_installed_battery(
        self,
        quiescent_ma: float,
        alarm_ma: float,
        installed_battery_ah: float,
        battery_cells: int = 6,
        panel_ambient_temp_c: float = 25.0,
    ) -> Any:
        """Convenience method: audit an installed battery for adequacy.

        Args:
            quiescent_ma: Total standby current (mA).
            alarm_ma: Total alarm current (mA).
            installed_battery_ah: Battery rated capacity at 20h rate (Ah).
            battery_cells: Number of 2V cells (default 6 = 12V).
            panel_ambient_temp_c: Minimum ambient temperature (°C).

        Returns:
            DecisionProvenance or dict with audit result.

        """
        return self.calculate_minimum_ah(
            quiescent_ma=quiescent_ma,
            alarm_ma=alarm_ma,
            panel_ambient_temp_c=panel_ambient_temp_c,
            installed_battery_ah=installed_battery_ah,
            battery_cells=battery_cells,
        )
