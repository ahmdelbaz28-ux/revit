# Revit Connector for FireAlarmAI Governance Engine

## Purpose
This Add-in extracts regulatory-sensitive spatial data from Autodesk Revit and 
exports it as CanonicalGeoSnapshot JSON files compatible with the FireAlarmAI 
Governance Engine and the Standalone Deterministic Verifier.

## Architecture Freeze Compliance
- The mapping table `REVIT_TO_GEOGRAPH` is **FROZEN**.
- Any modification requires governance process approval.
- Unrecognized Revit families **abort the export** to prevent semantic drift.

## Setup (with Revit 2024+)

1. Install the Revit SDK.
2. Create a new Class Library project in Visual Studio targeting .NET Framework 4.8.
3. Add references to `RevitAPI.dll` and `RevitAPIUI.dll`.
4. Implement the `IExternalCommand` interface to call `ExportZone()` for each Room.
5. Register the Add-in via a `.addin` manifest file.

## Python Equivalent (Testing)
For testing without Revit, use the Python modules in `src/`:
```bash
python3 tests/test_translator.py
```

## JSON Output Format
Each exported zone produces:

```json
{
    "snapshot": {
        "zone_id": "Room_101",
        "width": 10.0,
        "height": 10.0,
        "ceiling_slope": 0.0,
        "detectors": [{"id": "DET_01", "x": 3.5, "y": 4.2}],
        "obstacles": [{"x1": 5.0, "y1": 0.0, "x2": 5.0, "y2": 10.0, "is_solid_wall": true}],
        "doors": [{"x1": 5.0, "y1": 0.0, "x2": 5.0, "y2": 0.9, "semantics": "FireDoor"}]
    },
    "geo_hash": "635d6738b8..."
}
```

## Canonical Rounding
All coordinates are rounded to 6 decimal places before hashing to prevent
cross-platform floating-point drift.