"""marine/iso15370 — ISO 15370 thermal alarms for passenger ships."""
from marine.iso15370.thermal_alarms import (
    calculate_thermal_alarm_count,
    select_thermal_alarm_class,
)

__all__ = ["calculate_thermal_alarm_count", "select_thermal_alarm_class"]
