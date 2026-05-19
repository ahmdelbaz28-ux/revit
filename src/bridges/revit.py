"""
bridges/revit.py
================
Bidirectional Revit bridge.

Pure-Python cannot call Revit API directly (it's .NET). The standard,
production-grade pattern is a **command-file protocol**:

  ┌──────────┐  IFC/JSON  ┌──────────────┐  C#/IronPython  ┌─────────┐
  │  Python  │ ─────────▶ │  fsg.commands│ ──────────────▶ │  Revit  │
  │  FSG     │ ◀───────── │  fsg.results │ ◀────────────── │ Add-in  │
  └──────────┘            └──────────────┘                 └─────────┘

What Python does:
  1. Reads an IFC export of the Revit model (`ifcopenshell`).
  2. Builds a DigitalTwin and runs full analysis.
  3. Writes a Revit COMMAND FILE (`<project>.fsg.commands.json`):
       - tag findings on specific elements (by IFC GUID → Revit Element ID)
       - add Parameters: FSG_Status, FSG_Confidence, FSG_FindingHash
       - create View Filters that color elements by severity
       - add Schedules listing all FSG-flagged elements

A small pyRevit / Dynamo / C# add-in (template provided) reads the file
and applies the commands in Revit.

The roundtrip back (engineer fixes things → re-export IFC → re-analyze)
closes the loop.
"""
from __future__ import annotations
import json, logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────
def ifc_to_twin(ifc_path: str):
    """Read an IFC file and build a DigitalTwin (rooms + devices).

    V8: DISABLED - use v8_core modules instead.
    """
    raise RuntimeError("V8: ifc_to_twin disabled. Use v8_core modules for building analysis.")
    # try:
    #     import ifcopenshell
    #     import ifcopenshell.util.placement as placement
    # except ImportError:
    #     raise RuntimeError("ifcopenshell required: pip install ifcopenshell")
    # from ..digital_twin.twin import DigitalTwin, Room, Device, Opening

    m = ifcopenshell.open(ifc_path)
    t = DigitalTwin()

    # Spaces → rooms (best-effort; only get center + name for now)
    for sp in m.by_type("IfcSpace"):
        cy_height = 2.8
        psets = _get_psets(sp)
        for ps in psets.values():
            cy_height = float(ps.get("Height", ps.get("CeilingHeight", 2.8)) or 2.8)
            break
        try:
            mat = placement.get_local_placement(sp.ObjectPlacement)
            cx, cy = float(mat[0,3]), float(mat[1,3])
            poly = [(cx-3,cy-3),(cx+3,cy-3),(cx+3,cy+3),(cx-3,cy+3)]
        except Exception:
            poly = [(0,0),(6,0),(6,6),(0,6)]
        t.add_room(Room(id=sp.GlobalId, name=sp.Name or sp.LongName or sp.GlobalId,
                        polygon=poly, ceiling_height_m=cy_height,
                        use=(sp.LongName or "office").lower()))

    # Sensors / detectors / cameras
    sensor_types = ("IfcSensor","IfcAlarm","IfcDetector","IfcController",
                    "IfcAudioVisualAppliance","IfcLightFixture","IfcSwitchingDevice")
    for sym in sensor_types:
        for el in m.by_type(sym):
            try:
                mat = placement.get_local_placement(el.ObjectPlacement)
                pos = (float(mat[0,3]), float(mat[1,3]))
                z   = float(mat[2,3])
            except Exception:
                pos = (0,0); z = 2.8
            kind = _ifc_to_symbol(el)
            t.add_device(Device(id=el.GlobalId, kind=kind, position=pos,
                                 mounting_height_m=z,
                                 attributes={"ifc_class": el.is_a(),
                                              "name": el.Name or ""}))
    return t


def _ifc_to_symbol(el) -> str:
    name = (el.Name or "").lower()
    typ  = el.is_a().lower()
    if "smoke" in name: return "smoke_detector"
    if "heat"  in name: return "heat_detector"
    if "sprink" in name: return "sprinkler_pendant"
    if "camera" in name or "cctv" in name: return "camera_dome"
    if "ifclightfixture" in typ: return "light_fixture"
    if "ifcsensor" in typ: return "smoke_detector"  # conservative
    return "unknown_ifc"


def _get_psets(product) -> dict:
    out = {}
    for rel in getattr(product, "IsDefinedBy", []) or []:
        if rel.is_a("IfcRelDefinesByProperties"):
            pdef = rel.RelatingPropertyDefinition
            if pdef.is_a("IfcPropertySet"):
                ps = {}
                for p in pdef.HasProperties:
                    if hasattr(p, "NominalValue") and p.NominalValue:
                        ps[p.Name] = p.NominalValue.wrappedValue
                out[pdef.Name] = ps
    return out


# ──────────────────────────────────────────────────────────────────────────
# Command file for the Revit add-in
# ──────────────────────────────────────────────────────────────────────────
def write_revit_commands(report_canonical: dict, out_path: str,
                          twin = None) -> str:
    """Generate a JSON command file the Revit add-in consumes."""
    commands = []

    # 1) Parameter values per element (by IFC GUID)
    for f in report_canonical.get("findings", []):
        ev = f.get("evidence") or {}
        for key in ("ifc_guid","global_id","element_guid"):
            if isinstance(ev, dict) and key in ev:
                commands.append({
                    "op": "set_parameters",
                    "element_guid": ev[key],
                    "parameters": {
                        "FSG_Status":     f["severity"].upper(),
                        "FSG_Rule":       f["rule"],
                        "FSG_Message":    f["message"][:255],
                        "FSG_Citation":   f.get("citation",""),
                        "FSG_Hash":       f.get("hash","")[:16],
                        "FSG_Version":    report_canonical.get("software",""),
                    }
                })

    # 2) View filters that color elements by severity
    for sev, color in [("critical","255,0,0"),("major","255,140,0"),
                       ("minor","255,220,0"),("advisory","65,130,255")]:
        commands.append({
            "op": "create_view_filter",
            "name": f"FSG_{sev.title()}",
            "rule": {"parameter":"FSG_Status","equals":sev.upper()},
            "color_rgb": color, "weight": 6,
        })

    # 3) Schedule of FSG-flagged elements
    commands.append({
        "op": "create_schedule",
        "name": "FSG — Findings",
        "category": "Generic Models",
        "fields": ["FSG_Status","FSG_Rule","FSG_Message","FSG_Hash"],
        "filter": {"FSG_Status":"<>NULL"},
    })

    # 4) Sheet annotation with overall verdict
    commands.append({
        "op": "place_text_note",
        "sheet": "FSG-001",   # add-in creates this sheet
        "text": (f"FireSafetyGenius analysis\\n"
                 f"Verdict: {report_canonical.get('reasoning',{}).get('conclusion','—')}\\n"
                 f"Critical: {sum(1 for f in report_canonical['findings'] if f['severity']=='critical')}\\n"
                 f"Chain root: {report_canonical['integrity']['chain_root'][:16]}…"),
    })

    payload = {
        "schema": "fsg-revit-commands-1.0",
        "issued_at": report_canonical["integrity"]["issued_at_utc"],
        "issuer":   report_canonical["issuer"],
        "chain_root": report_canonical["integrity"]["chain_root"],
        "commands": commands,
    }
    Path(out_path).write_text(json.dumps(payload, indent=2, default=str))
    log.info("Wrote %d Revit commands → %s", len(commands), out_path)
    return out_path


# ──────────────────────────────────────────────────────────────────────────
# Companion C# add-in template (write to disk for the user)
REVIT_ADDIN_CS = r"""
// FireSafetyGenius Revit Add-in (C# / .NET 4.8+ / Revit 2022+)
// Build: target Revit API DLLs RevitAPI.dll + RevitAPIUI.dll
// Drop the resulting .dll + .addin into %AppData%\Autodesk\Revit\Addins\<year>\
using System;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json.Linq;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

[Transaction(TransactionMode.Manual)]
public class ApplyFSGCommands : IExternalCommand {
  public Result Execute(ExternalCommandData data, ref string msg, ElementSet els) {
    var uidoc = data.Application.ActiveUIDocument;
    var doc = uidoc.Document;
    var dlg = new Microsoft.Win32.OpenFileDialog { Filter = "FSG commands|*.commands.json" };
    if (dlg.ShowDialog() != true) return Result.Cancelled;
    var json = JObject.Parse(File.ReadAllText(dlg.FileName));
    using (var tx = new Transaction(doc, "Apply FSG commands")) {
      tx.Start();
      foreach (var c in json["commands"]) {
        var op = c["op"].ToString();
        if (op == "set_parameters") ApplyParameters(doc, c);
        else if (op == "create_view_filter") CreateViewFilter(doc, c);
        // ... etc
      }
      tx.Commit();
    }
    TaskDialog.Show("FSG","Applied commands from " + dlg.FileName);
    return Result.Succeeded;
  }

  void ApplyParameters(Document doc, JToken c) {
    var guid = c["element_guid"].ToString();
    var el = doc.GetElement(guid);
    if (el == null) return;
    foreach (var kv in (JObject)c["parameters"]) {
      var p = el.LookupParameter(kv.Key);
      if (p != null && !p.IsReadOnly) p.Set(kv.Value.ToString());
    }
  }
  void CreateViewFilter(Document doc, JToken c) {
    // Skeleton — see Revit API docs for ParameterFilterElement
  }
}
"""

def write_revit_addin_template(out_path: str) -> str:
    """Drop the C# add-in source for the user to compile."""
    Path(out_path).write_text(REVIT_ADDIN_CS)
    return out_path
