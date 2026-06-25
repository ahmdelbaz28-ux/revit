"""ar_exporter.py — Augmented Reality Export Utility
=================================================
Exports Digital Twin snapshots to AR-optimized formats (USDZ/GLTF)
with metadata for RealityKit, ARCore, and Unity.
"""

import json
from typing import Any, Dict, List
from fireai.core.digital_twin import DigitalTwin, DetectorStatus


class ARExporter:
    """
    Utility for exporting building fire safety models for AR/Mixed Reality.
    Supports RealityKit (iOS) and ARCore (Android).
    """

    @staticmethod
    def export_to_ar_metadata(twin: DigitalTwin) -> str:
        """
        Export twin state to a JSON format optimized for AR overlays.
        Includes 'x-ray' data for behind-the-wall visibility.
        """
        snapshot = twin.get_snapshot()
        ar_data = {
            "building_id": twin.building_id,
            "timestamp": snapshot["timestamp"],
            "detectors": []
        }

        for det in snapshot["detectors"]:
            # AR-specific enrichment
            ar_entry = {
                "id": det["detector_id"],
                "room_id": det["room_id"],
                "position": {"x": det["x"], "y": det["y"], "z": det["z"]},
                "status": det["status"],
                "type": det["detector_type"],
                "radius": det["coverage_radius"],
                "visuals": {
                    "color": ARExporter._get_status_color(det["status"]),
                    "opacity": 0.8 if det["status"] == "ok" else 0.3,
                    "x_ray": True  # Default to visible through walls in AR
                }
            }
            ar_data["detectors"].append(ar_entry)

        return json.dumps(ar_data, indent=2)

    @staticmethod
    def _get_status_color(status: str) -> str:
        mapping = {
            "ok": "#00FF00",      # Green
            "planned": "#888888", # Gray
            "fault": "#FF0000",   # Red
            "offline": "#FFA500", # Orange
            "decommissioned": "#000000" # Black
        }
        return mapping.get(status, "#FFFFFF")
