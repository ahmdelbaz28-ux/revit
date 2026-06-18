"""marine/integration/etap_bridge.py — ETAP Power System Integration.
Exports ship electrical model (fire-system loads + UPS + redundancy) to ETAP
.ort project format (CSV-based intermediate) for power-system analysis."""
from __future__ import annotations
import csv
import io
from typing import List
from marine.core.types import ShipElectricalSpec, ShipProject


def export_etap_loads_csv(
    ship: ShipProject, spec: ShipElectricalSpec,
    detection_load_w: float = 500.0, alarm_load_w: float = 1000.0,
    extinguish_load_w: float = 2000.0,
) -> str:
    """Export fire-system loads as ETAP-compatible CSV."""
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(["Bus", "Load_Name", "Type", "kW", "pf", "Category"])
    w.writerow(["FIRE-MDB", "Detection_System", "Static", f"{detection_load_w/1000:.3f}", "0.9", "Essential"])
    w.writerow(["FIRE-MDB", "Alarm_Devices", "Static", f"{alarm_load_w/1000:.3f}", "0.9", "Essential"])
    w.writerow(["FIRE-MDB", "Extinguishing_Control", "Static", f"{extinguish_load_w/1000:.3f}", "0.85", "Essential"])
    w.writerow(["FIRE-UPS", "UPS_Bank", "Storage", f"{spec.ups_capacity_ah * 0.024:.2f}", "1.0", "Backup"])
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
