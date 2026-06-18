"""marine/iso15370/thermal_alarms.py — ISO 15370 Thermal Alarms.
ISO 15370: Ships and marine technology — Thermal alarms for passenger ships.
Provides thermal-alarm spacing and temperature-class selection for escape
routes on passenger ships carrying >36 passengers."""
from __future__ import annotations
from marine.core.constants import (
    THERMAL_ALARM_MAX_SPACING_M, THERMAL_ALARM_RESPONSE_C,
)
from marine.core.types import ComplianceResult, MarineZone, ThermalAlarmClass

def select_thermal_alarm_class(ambient_temp_c: float) -> ThermalAlarmClass:
    """Pick Class A (70°C) or B (90°C) based on ambient temperature."""
    if ambient_temp_c < 40:
        return ThermalAlarmClass.CLASS_A
    return ThermalAlarmClass.CLASS_B

def calculate_thermal_alarm_count(zone: MarineZone) -> ComplianceResult:
    """Calculate thermal alarms needed in a passenger-ship escape route."""
    result = ComplianceResult(
        compliant=True, standard_reference="ISO 15370 §6",
    )
    count = max(1, int(zone.area_m2 / (THERMAL_ALARM_MAX_SPACING_M ** 2)))
    result.details["alarm_count"] = count
    result.details["max_spacing_m"] = THERMAL_ALARM_MAX_SPACING_M
    return result

__all__ = ["select_thermal_alarm_class", "calculate_thermal_alarm_count"]
