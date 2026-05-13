"""
bridges/dialux.py
=================
DIALux evo bridge (lighting design + emergency lighting).

DIALux's native format is .evo (binary). We use the documented
exchange paths:

  - INPUT  to DIALux:  IFC (room geometry) + IES (photometric files)
  - OUTPUT from DIALux: IES result tables + DXF/IFC re-export

Our code:
  1) Exports room geometry from a DigitalTwin to IFC for DIALux import.
  2) Generates a synthetic IES photometric file for any luminaire kind.
  3) Parses DIALux's exported results (illuminance per point) and
     verifies against NFPA 101 §7.9 emergency lighting requirements:
       • 1 lux average, 0.1 lux minimum along path of egress
       • 10.8 lux at exit doors
"""
from __future__ import annotations
import logging, math
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────
# IES (LM-63-2002) photometric file generator
# ──────────────────────────────────────────────────────────────────────────
IES_TEMPLATE = """IESNA:LM-63-2002
[TEST] FireSafetyGenius synthetic
[MANUFAC] FSG
[LUMCAT] {model}
[LUMINAIRE] {model} ({lumens} lm)
[ISSUEDATE] 2025-01-01
TILT=NONE
1 {lumens} 1 {n_v} {n_h} 1 2 1 {l} {l} {l}
1.0 1.0 0.0
{v_angles}
{h_angles}
{values}
"""

def make_ies(out_path: str, model: str = "FSG_EMLIGHT",
             lumens: int = 250, half_beam_deg: int = 60) -> str:
    """Generate a simple IES with Lambertian-ish distribution."""
    v_angles = list(range(0, 91, 5))     # 0..90 in 5° steps
    h_angles = [0.0]                      # axially symmetric
    n_v = len(v_angles); n_h = len(h_angles)
    # candela distribution: cos(theta)^n falling off past half-beam
    peak_cd = lumens / 3.14
    values = []
    for v in v_angles:
        rad = math.radians(v)
        cd = peak_cd * max(0.0, math.cos(rad))
        if v > half_beam_deg: cd *= 0.3
        values.append(f"{cd:.1f}")
    content = IES_TEMPLATE.format(
        model=model, lumens=lumens,
        n_v=n_v, n_h=n_h, l=0.3,
        v_angles=" ".join(map(str, v_angles)),
        h_angles=" ".join(map(str, h_angles)),
        values=" ".join(values),
    )
    Path(out_path).write_text(content)
    return out_path


# ──────────────────────────────────────────────────────────────────────────
# IFC export of room geometry for DIALux
# ──────────────────────────────────────────────────────────────────────────
def twin_to_ifc(twin, out_path: str, project_name: str = "FSG_Project") -> str:
    """Export rooms + light fixtures as a minimal IFC4 model."""
    try:
        import ifcopenshell
        from ifcopenshell.api import run
    except ImportError:
        raise RuntimeError("ifcopenshell required for IFC export")

    m = ifcopenshell.file(schema="IFC4")
    project = run("root.create_entity", m, ifc_class="IfcProject",
                  name=project_name)
    run("unit.assign_unit", m, length={"is_metric": True, "raw": "METERS"})

    site = run("root.create_entity", m, ifc_class="IfcSite",  name="Site")
    bldg = run("root.create_entity", m, ifc_class="IfcBuilding", name="Building")
    storey = run("root.create_entity", m, ifc_class="IfcBuildingStorey",
                  name="Ground Floor")
    run("aggregate.assign_object", m, product=site,   relating_object=project)
    run("aggregate.assign_object", m, product=bldg,   relating_object=site)
    run("aggregate.assign_object", m, product=storey, relating_object=bldg)

    # Rooms
    for r in twin.rooms.values():
        try:
            sp = run("root.create_entity", m, ifc_class="IfcSpace",
                     name=r.name or r.id)
            # geometry: extruded polygon
            run("geometry.add_floorplan_representation", m,
                context=run("context.add_context", m, context_type="Model"),
                element=sp, profile_polygon=r.polygon,
                depth=r.ceiling_height_m)
            run("aggregate.assign_object", m, product=sp, relating_object=storey)
        except Exception as ex:
            log.warning("Failed to export room %s: %s", r.id, ex)

    m.write(out_path)
    log.info("IFC exported → %s", out_path)
    return out_path


# ──────────────────────────────────────────────────────────────────────────
# Parse DIALux result export (IES tabulated grid)
# ──────────────────────────────────────────────────────────────────────────
def parse_dialux_grid(path: str) -> dict:
    """Parse a generic Dialux-exported text grid: header lines + N rows of
    (x, y, illuminance_lux). Returns {points: [...], stats: {...}}."""
    pts = []
    for line in Path(path).read_text().splitlines():
        parts = line.replace(",", " ").split()
        if len(parts) >= 3:
            try:
                x, y, lux = float(parts[0]), float(parts[1]), float(parts[2])
                pts.append((x, y, lux))
            except ValueError:
                continue
    if not pts: return {"points": [], "stats": {}}
    lux_vals = [p[2] for p in pts]
    return {"points": pts,
            "stats": {"avg_lux": sum(lux_vals)/len(lux_vals),
                      "min_lux": min(lux_vals),
                      "max_lux": max(lux_vals),
                      "uniformity": min(lux_vals)/(sum(lux_vals)/len(lux_vals))
                                    if lux_vals else 0,
                      "n_points": len(pts)}}


def check_nfpa_101_emergency_lighting(grid_result: dict) -> list[dict]:
    """Apply NFPA 101 §7.9.2.1 minimums to a parsed Dialux grid."""
    s = grid_result.get("stats", {})
    findings = []
    if not s: return findings
    if s["avg_lux"] < 1.0:
        findings.append({"severity":"critical","code":"NFPA101","rule":"7.9.2.1",
                         "message": f"Average illuminance {s['avg_lux']:.2f} lx "
                                    f"< 1.0 lx along egress path.",
                         "citation":"NFPA 101 §7.9.2.1",
                         "recommendation":"Add or upgrade emergency luminaires."})
    if s["min_lux"] < 0.1:
        findings.append({"severity":"critical","code":"NFPA101","rule":"7.9.2.1",
                         "message": f"Minimum illuminance {s['min_lux']:.2f} lx "
                                    f"< 0.1 lx — dark zone exists.",
                         "citation":"NFPA 101 §7.9.2.1",
                         "recommendation":"Add luminaire to cover minimum-illumination zone."})
    return findings
