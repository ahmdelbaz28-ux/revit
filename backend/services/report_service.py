"""
Report generation service — business logic extracted from routers/reports.py.

This module contains the report generation logic that was previously embedded
in the reports router. Extracting it makes the logic testable in isolation
and follows the "thin routers" architecture principle.

P2.3 FIX: Business logic moved here from backend/routers/reports.py:49-204.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

# NFPA 72 alarm device types (notification appliances)
# Per NFPA 72 §27.6.2: alarm load = notification appliances active for 5 min
ALARM_DEVICE_TYPES: frozenset[str] = frozenset({
    "FA_SOUND_STROBE",     # Combined sounder/strobe — PRIMARY evacuation signal
    "FA_HORN",            # Fire alarm horn
    "FA_STROBE",          # Visual alarm strobe
    "FA_BELL",            # Fire alarm bell
    "FA_SIREN",           # Electronic siren
    "PA_CEILING_SPEAKER", # PA speaker used for voice evacuation
    "PA_WALL_SPEAKER",    # Wall-mounted PA speaker for voice evacuation
    "PA_HORN",            # Outdoor horn for voice evacuation
})

# Categories that typically contain voice alarm devices
ALARM_CATEGORIES: frozenset[str] = frozenset({"PA_SYSTEM"})

# PA devices that are NOT alarm appliances (amplifiers, microphones)
PA_NON_ALARM_TYPES: frozenset[str] = frozenset({"PA_AMPLIFIER", "PA_MICROPHONE"})


def count_by_category(devices: List[Dict[str, Any]]) -> Dict[str, int]:
    """Count devices by category.

    Args:
        devices: List of device dictionaries with 'category' key.

    Returns:
        Dictionary mapping category → count.
    """
    counts: Dict[str, int] = {}
    for d in devices:
        cat = d.get("category", "unknown")
        counts[cat] = counts.get(cat, 0) + 1
    return counts


def classify_device_load(device: Dict[str, Any]) -> tuple[float, str]:
    """Classify a device's load as alarm or standby per NFPA 72 §27.6.2.

    Args:
        device: Device dictionary with 'load', 'type', and 'category' keys.

    Returns:
        Tuple of (load_amperes, role) where role is 'alarm' or 'standby'.
    """
    load = float(device.get("load", 0) or 0)
    device_type = device.get("type", "")
    device_category = device.get("category", "")

    is_alarm = (
        device_type in ALARM_DEVICE_TYPES
        or device_category == "notification"  # Legacy compatibility
        or (device_category in ALARM_CATEGORIES and device_type not in PA_NON_ALARM_TYPES)
    )

    return (load, "alarm" if is_alarm else "standby")


def calculate_battery_capacity(
    devices: List[Dict[str, Any]],
    standby_hours: float = 24.0,
    alarm_minutes: float = 15.0,
    derating_factor: float = 0.80,
) -> Dict[str, Any]:
    """Calculate required battery capacity per NFPA 72 §27.6.2.

    Args:
        devices: List of device dictionaries.
        standby_hours: Standby duration (default 24h per §10.6.7.2.1).
        alarm_minutes: Alarm duration (default 15 min for voice evacuation).
        derating_factor: Battery derating for aging/temperature (default 0.80).

    Returns:
        Dictionary with battery calculation results.

    SAFETY NOTE: All load values are assumed to be in Amperes (A).
    If any device load was entered in milliAmperes (mA) or Watts (W),
    the battery calculation will be incorrect. Verify all device loads
    before relying on this calculation for life-safety decisions.
    """
    total_standby = 0.0
    total_alarm = 0.0

    for d in devices:
        load, role = classify_device_load(d)
        if role == "alarm":
            total_alarm += load
        else:
            total_standby += load

    # BUG-29 FIX: Previous condition `if total_standby > 0 else 0` returned
    # zero battery when only notification appliances exist. NFPA 72 §27.6.2
    # requires battery capacity for alarm load regardless of standby load.
    if total_standby > 0 or total_alarm > 0:
        battery_ah = (
            total_standby * standby_hours
            + total_alarm * (alarm_minutes / 60.0)
        ) / derating_factor
    else:
        battery_ah = 0.0

    return {
        "standbyLoadA": round(total_standby, 6),
        "alarmLoadA": round(total_alarm, 6),
        "standbyHours": standby_hours,
        "alarmMinutes": alarm_minutes,
        "deratingFactor": derating_factor,
        "requiredAh": round(battery_ah, 3),
        "unitAssumption": "A",
        "safetyWarning": (
            "All load values are assumed to be in Amperes (A). "
            "If any device load was entered in milliAmperes (mA) or Watts (W), "
            "the battery calculation will be incorrect. Verify all device loads "
            "before relying on this calculation for life-safety decisions."
        ),
    }


def generate_voltage_drop_report(
    devices: List[Dict[str, Any]],
    connections: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Generate voltage drop report data.

    Args:
        devices: List of device dictionaries.
        connections: List of connection dictionaries with fromId, toId, cableSize, length.

    Returns:
        Dictionary with voltage drop circuit data.
    """
    # Use dict lookup for O(1) per device (was O(n) linear scan per connection)
    device_map = {d["id"]: d for d in devices}
    circuits = []

    for conn in connections:
        from_dev = device_map.get(conn.get("fromId"))
        to_dev = device_map.get(conn.get("toId"))
        if from_dev and to_dev:
            circuits.append({
                "from": from_dev["name"],
                "to": to_dev["name"],
                "cableSize": conn["cableSize"],
                "length": conn["length"],
                "load": to_dev.get("load", 0),
                "voltage": to_dev.get("voltage", 0),
            })

    return {
        "type": "voltage_drop",
        "standard": "IEC 60364 / NFPA 72-2022 §27.4.1.2",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "totalCircuits": len(circuits),
        "circuits": circuits,
    }


def generate_nfpa72_coverage_report(devices: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate NFPA 72 coverage report data.

    Args:
        devices: List of device dictionaries.

    Returns:
        Dictionary with coverage analysis data.
    """
    return {
        "type": "nfpa72_coverage",
        "standard": "NFPA 72-2022",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "totalDevices": len(devices),
        "devicesByCategory": count_by_category(devices),
        "complianceNotes": [
            "All detector placements must be verified by a licensed FPE",
            "Coverage calculations assume standard ceiling conditions",
        ],
    }


def generate_nfpa72_battery_report(devices: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate NFPA 72 battery calculation report.

    Args:
        devices: List of device dictionaries.

    Returns:
        Dictionary with battery calculation per NFPA 72 §27.6.2.
    """
    battery_data = calculate_battery_capacity(devices)
    return {
        "type": "nfpa72_battery",
        "standard": "NFPA 72-2022 §27.6.2",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        **battery_data,
    }


def generate_cable_sizing_report(connections: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate cable sizing report data.

    Args:
        connections: List of connection dictionaries.

    Returns:
        Dictionary with cable sizing data.
    """
    return {
        "type": "cable_sizing",
        "standard": "IEC 60364 / NFPA 70",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "totalConnections": len(connections),
        "connections": [
            {
                "id": c["id"],
                "cableSize": c["cableSize"],
                "length": c["length"],
                "type": c["type"],
            }
            for c in connections
        ],
    }


def generate_generic_report(
    report_type: str,
    devices: List[Dict[str, Any]],
    connections: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Generate a generic report with project summary.

    Args:
        report_type: Report type string.
        devices: List of device dictionaries.
        connections: List of connection dictionaries.

    Returns:
        Dictionary with generic report data.
    """
    return {
        "type": report_type,
        "standard": "General Engineering Analysis",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "totalDevices": len(devices),
        "totalConnections": len(connections),
        "devicesByCategory": count_by_category(devices),
    }


def generate_report(
    report_type: str,
    devices: List[Dict[str, Any]],
    connections: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Generate report content based on type.

    This is the main entry point for report generation. It dispatches to
    the appropriate specialized generator based on report_type.

    Args:
        report_type: One of 'voltage_drop', 'nfpa72_coverage', 'nfpa72_battery',
                     'cable_sizing', or any other type (generates generic report).
        devices: List of device dictionaries.
        connections: List of connection dictionaries.

    Returns:
        Dictionary with report data.
    """
    if report_type == "voltage_drop":
        return generate_voltage_drop_report(devices, connections)
    elif report_type == "nfpa72_coverage":
        return generate_nfpa72_coverage_report(devices)
    elif report_type == "nfpa72_battery":
        return generate_nfpa72_battery_report(devices)
    elif report_type == "cable_sizing":
        return generate_cable_sizing_report(connections)
    else:
        return generate_generic_report(report_type, devices, connections)
