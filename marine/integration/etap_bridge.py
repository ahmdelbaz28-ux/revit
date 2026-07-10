"""
marine/integration/etap_bridge.py — ETAP Power System Integration.
Exports ship electrical model (fire-system loads + UPS + redundancy) to ETAP
.ort project format (CSV-based intermediate) for power-system analysis.
"""
from __future__ import annotations

import csv
import io

from marine.core.types import ShipElectricalSpec, ShipProject


def export_etap_loads_csv(
    ship: ShipProject, spec: ShipElectricalSpec,
    detection_load_w: float = 500.0, alarm_load_w: float = 1000.0,
    extinguish_load_w: float = 2000.0,
    ups_power_kw: float = 2.5,
) -> str:
    """
    Export fire-system loads as ETAP-compatible CSV.

    BUGFIX v2: previously computed UPS load as `ups_capacity_ah * 0.024`
    which yields kWh (Ah × V / 1000), not kW (real power). ETAP load-flow
    expects kW. Now accepts explicit `ups_power_kw` parameter (inverter
    power rating, which is what ETAP needs for steady-state load flow).

    Args:
        ship: Ship project (unused in this stub but kept for API stability
            and future scaling by zone count / ship size).
        spec: Ship electrical spec (for cross-reference of UPS capacity).
        detection_load_w: Detection system load in watts.
        alarm_load_w: Alarm devices load in watts.
        extinguish_load_w: Extinguishing control load in watts.
        ups_power_kw: Real power rating of the UPS inverter (kW). This is
            what ETAP's load-flow engine needs — it is unrelated to the
            battery's Ah capacity (which only determines autonomy duration).
            Default 2.5 kW (typical for a 500 W detection + 1 kW alarm +
            2 kW extinguishing system at 50% headroom).

    """
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(["Bus", "Load_Name", "Type", "kW", "pf", "Category"])
    w.writerow(["FIRE-MDB", "Detection_System", "Static", f"{detection_load_w/1000:.3f}", "0.9", "Essential"])
    w.writerow(["FIRE-MDB", "Alarm_Devices", "Static", f"{alarm_load_w/1000:.3f}", "0.9", "Essential"])
    w.writerow(["FIRE-MDB", "Extinguishing_Control", "Static", f"{extinguish_load_w/1000:.3f}", "0.85", "Essential"])
    # UPS rated power (kW) — this is the inverter's real-power output, not
    # the battery's energy capacity (Ah × V = Wh).
    w.writerow(["FIRE-UPS", "UPS_Inverter", "Static", f"{ups_power_kw:.2f}", "0.95", "Backup"])
    return output.getvalue()


def export_etap_sources_csv(spec: ShipElectricalSpec) -> str:
    """Export power sources for ETAP."""
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(["Source", "Type", "kV", "kVA", "X_R"])
    w.writerow(["MAIN-SWB", "Generator", f"{spec.main_supply_voltage/1000:.2f}", "500", "8.0"])
    w.writerow(["EMER-SWB", "Emergency_Gen", f"{spec.emergency_supply_voltage/1000:.2f}", "100", "6.0"])
    return output.getvalue()


__all__ = ["export_etap_loads_csv", "export_etap_sources_csv"]
