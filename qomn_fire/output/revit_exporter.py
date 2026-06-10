"""
QOMN-FIRE BIM EXCHANGE SCHEMA EXPORTER
"""

import json
from typing import List
from qomn_fire.core.types import Device, ConduitRun, PanelRecommendation

def export_to_revit_json(devices: List[Device], runs: List[ConduitRun], facp: PanelRecommendation) -> str:
    schema = {
        "SchemaVersion": "1.0",
        "Project": "QOMN-FIRE INTEGRATED EXPORT ENGINE",
        "SelectedFACP": {
            "Model": facp.recommended_model,
            "Manufacturer": facp.manufacturer,
            "RequiredBatteryAh": facp.battery_size_ah,
            "PointsUtilization": facp.capacity_utilization,
            "Signature": facp.signature_hash
        },
        "Devices": [],
        "ConduitRuns": []
    }

    for d in devices:
        schema["Devices"].append({
            "Id": d.id,
            "Type": d.device_type.value,
            "Location": d.location.to_dict(),
            "ElevationFt": d.elevation_ft,
            "Circuit": d.circuit,
            "Zone": d.zone,
            "Hash": d.compute_hash()
        })

    for r in runs:
        schema["ConduitRuns"].append({
            "Id": r.id,
            "ConduitType": r.conduit_type.value,
            "TradeSize": r.trade_size,
            "TotalLengthFt": r.total_length_ft,
            "BendCount": r.bend_count,
            "BendDegrees": r.bend_degrees,
            "Path": [p.to_dict() for p in r.points],
            "Hash": r.compute_hash()
        })

    return json.dumps(schema, indent=2, sort_keys=True)
