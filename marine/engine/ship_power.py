"""
marine/engine/ship_power.py — Ship Electrical Power for Fire Systems
=====================================================================
Moved from marine/iec60092/electrical_installations.py as part of M4
refactor. Contains fire-system power-supply design and insulation-
monitoring validation.

References:
    [IEC301] IEC 60092-301 — Main power generation & distribution
    [IEC502] IEC 60092-502 — Tankers electrical installations
    [IEC504] IEC 60092-504 — Ships carrying dangerous goods

"""
from __future__ import annotations

from marine.core.constants import (
    FIRE_SYSTEM_UPS_MIN_AUTONOMY_MIN,
    INSULATION_MONITOR_THRESHOLD_KOHM,
    SHIP_EMERGENCY_VOLTAGE_V,
    SHIP_LOW_VOLTAGE_V,
    SHIP_MAIN_VOLTAGE_V,
)
from marine.core.types import (
    ComplianceResult,
    ShipElectricalSpec,
    ShipProject,
)


def design_fire_system_power(
    _ship: ShipProject,  # NOSONAR — S1172: parameter retained for API stability
    detection_load_w: float = 500.0,
    alarm_load_w: float = 1000.0,
    extinguish_load_w: float = 2000.0,
) -> ShipElectricalSpec:
    """
    Design the power-supply architecture for fire systems.

    Per SOLAS II-2/5.1.3 + IEC 60092-502 §6.2:
      1. Main supply (440V AC) -> step-down to 230V AC -> 24V DC control
      2. Emergency switchboard backup (230V AC)
      3. UPS battery >=30 min autonomy for all fire systems
      4. Insulation monitoring device (IMD) at the distribution board

    Args:
        ship: Ship project.
        detection_load_w: Power draw of detection system (W).
        alarm_load_w:    Power draw of alarm devices (W).
        extinguish_load_w: Power draw of extinguishing control (W).

    Returns:
        ShipElectricalSpec with calculated UPS capacity.

    """
    total_load_w = detection_load_w + alarm_load_w + extinguish_load_w
    ups_capacity_ah = (total_load_w * FIRE_SYSTEM_UPS_MIN_AUTONOMY_MIN) / \
        (60.0 * SHIP_LOW_VOLTAGE_V) * 1.25

    return ShipElectricalSpec(
        main_supply_voltage=SHIP_MAIN_VOLTAGE_V,
        emergency_supply_voltage=SHIP_EMERGENCY_VOLTAGE_V,
        ups_capacity_ah=round(ups_capacity_ah, 1),
        ups_autonomy_min=FIRE_SYSTEM_UPS_MIN_AUTONOMY_MIN,
        redundancy_level=3,
        insulation_monitoring=True,
        standard_reference="IEC 60092-301/502 + SOLAS II-2/5.1.3",
    )


def validate_insulation_monitoring(
    spec: ShipElectricalSpec,
    ship: ShipProject | None = None,
) -> ComplianceResult:
    """
    Validate insulation monitoring per IEC 60092-504 §5.

    Required for all ships carrying dangerous goods (tankers). Threshold:
    alarm at insulation resistance < 100 k Ohm.

    Args:
        spec: Ship electrical spec to validate.
        ship: Optional ShipProject — if provided, the IMD requirement is
            enforced strictly only when ``ship.is_tanker`` is True.

    """
    result = ComplianceResult(
        compliant=True,
        standard_reference="IEC 60092-504 §5 + SOLAS II-2/5.1.3",
    )

    imd_mandatory = ship is None or ship.is_tanker
    if not spec.insulation_monitoring:
        if imd_mandatory:
            result.add_finding(
                "Insulation monitoring device (IMD) is mandatory per IEC 60092-504 §5 "
                "for ships carrying dangerous goods (tankers)."
            )
        else:
            result.add_warning(
                "Insulation monitoring device (IMD) is recommended for all ships "
                "even when not strictly required by IEC 60092-504."
            )

    if spec.ups_autonomy_min < FIRE_SYSTEM_UPS_MIN_AUTONOMY_MIN:
        result.add_finding(
            f"UPS autonomy {spec.ups_autonomy_min:.1f} min is below the SOLAS "
            f"II-2/5.1.3 minimum of {FIRE_SYSTEM_UPS_MIN_AUTONOMY_MIN:.0f} min "
            f"for fire-detection and alarm systems."
        )

    result.details["alarm_threshold_kohm"] = INSULATION_MONITOR_THRESHOLD_KOHM
    result.details["voltage_main_v"] = spec.main_supply_voltage
    result.details["voltage_emergency_v"] = spec.emergency_supply_voltage
    result.details["ups_capacity_ah"] = spec.ups_capacity_ah
    result.details["ups_autonomy_min"] = spec.ups_autonomy_min
    result.details["imd_mandatory"] = imd_mandatory
    return result


__all__ = ["design_fire_system_power", "validate_insulation_monitoring"]
