"""marine/iec60092 — IEC 60092 series (ship electrical & fire detection)."""
from marine.iec60092.electrical_installations import (
    design_fire_system_power,
    validate_insulation_monitoring,
)
from marine.iec60092.part_502 import (
    calculate_detector_count,
    place_detectors_grid,
    select_detector_type,
    validate_alarm_circuit_redundancy,
)
from marine.iec60092.part_504 import (
    classify_hazardous_zone,
    select_intrinsically_safe_equipment,
)

__all__ = [
    "calculate_detector_count", "classify_hazardous_zone",
    "design_fire_system_power", "place_detectors_grid",
    "select_detector_type", "select_intrinsically_safe_equipment",
    "validate_alarm_circuit_redundancy", "validate_insulation_monitoring",
]
