"""
QOMN-FIRE REVIT CAD SYNC EXPORTER LAYER
"""

import json
from typing import List
from qomn_fire.core.types import Device, ConduitRun

def export_to_revit_json(devices: List[Device], runs: List[ConduitRun]) -> str:
    schema = {
        "SchemaVersion": "1.0",
        "Project": "QOMN-FIRE EXPORT ENGINE",
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
            "Bends": r.bend_count,
            "Path": [p.to_dict() for p in r.points],
            "Hash": r.compute_hash()
        })

    return json.dumps(schema, indent=2, sort_keys=True)
