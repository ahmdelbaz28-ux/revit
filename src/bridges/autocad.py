"""
bridges/autocad.py
==================
Bidirectional AutoCAD bridge.

Two channels:
  - READ:  ezdxf (already used in kernel.ingest) — pulls geometry, blocks, layers
  - WRITE: round-trip DXF with a NEW layer "FSG_FINDINGS" containing
           coloured circles + MTEXT annotations for every finding,
           so engineers can open the original drawing in AutoCAD and
           see the analysis OVERLAID on their geometry.

If full AutoCAD COM control is needed (Windows + AutoCAD running),
use the optional `comtypes` backend (kept as a stub here for portability).
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class MarkupOptions:
    layer_name:    str = "FSG_FINDINGS"
    layer_color:   int = 1     # ACI red
    text_height:   float = 250 # drawing units
    circle_radius: float = 400


# ──────────────────────────────────────────────────────────────────────────
def write_findings_to_dxf(src_dxf_path: str, out_dxf_path: str,
                          findings: list[dict],
                          elements: Optional[list[dict]] = None,
                          options: Optional[MarkupOptions] = None) -> str:
    """Open source DXF, add a markup layer with all findings, save copy."""
    try:
        import ezdxf
        from ezdxf.colors import RGB
    except ImportError:
        raise RuntimeError("ezdxf required: pip install ezdxf")
    options = options or MarkupOptions()

    doc = ezdxf.readfile(src_dxf_path)
    msp = doc.modelspace()
    if options.layer_name not in doc.layers:
        doc.layers.add(name=options.layer_name, color=options.layer_color)

    sev_colors = {"critical": 1, "major": 6, "minor": 2,
                  "advisory": 5, "info": 8}

    # Map element index → (cx, cy) for findings that reference elements by index
    el_pos = {}
    if elements:
        for i, el in enumerate(elements):
            bbox = el.get("bbox") or [0,0,0,0]
            el_pos[i] = ((bbox[0]+bbox[2])/2, (bbox[1]+bbox[3])/2)

    placed = 0
    for f in findings:
        sev = f.get("severity", "advisory")
        color = sev_colors.get(sev, 8)
        ev = f.get("evidence") or {}
        # Try to find a position
        i = ev.get("i") if isinstance(ev, dict) else None
        if i is not None and i in el_pos:
            cx, cy = el_pos[i]
        else:
            continue

        # Draw a marker circle
        msp.add_circle(center=(cx, cy), radius=options.circle_radius,
                       dxfattribs={"layer": options.layer_name, "color": color})
        # Label
        label = f"[{sev.upper()}] {f.get('rule','')}\\n{f.get('message','')[:80]}"
        msp.add_mtext(label,
                      dxfattribs={"layer": options.layer_name,
                                  "color": color,
                                  "char_height": options.text_height,
                                  "insert": (cx + options.circle_radius*1.3, cy)})
        placed += 1

    # Add a legend block in the corner
    _add_legend(msp, options, sev_colors)
    doc.saveas(out_dxf_path)
    log.info("Wrote %d findings → %s", placed, out_dxf_path)
    return out_dxf_path


def _add_legend(msp, opts, sev_colors):
    text = ("FIRE SAFETY GENIUS — MARKUP\\n"
            "Critical (red) | Major (orange) | Minor (yellow) | Advisory (blue)\\n"
            "This overlay is for engineer review. Do not assume PASS.")
    msp.add_mtext(text, dxfattribs={"layer": opts.layer_name, "color": 1,
                                     "char_height": opts.text_height*1.3,
                                     "insert": (0, 0)})


# ──────────────────────────────────────────────────────────────────────────
# Round-trip: changes engineers make on the FSG_FINDINGS layer are kept
def merge_engineer_edits(annotated_dxf: str, fsg_layer="FSG_FINDINGS") -> list[dict]:
    """Parse engineer-edited annotations back into structured corrections.
    Each MTEXT on the FSG_FINDINGS layer becomes a feedback record."""
    try:
        import ezdxf
    except ImportError:
        raise RuntimeError("ezdxf required")
    doc = ezdxf.readfile(annotated_dxf)
    msp = doc.modelspace()
    out = []
    for e in msp.query(f"MTEXT[layer=='{fsg_layer}']"):
        try:
            txt = e.plain_text() if hasattr(e, "plain_text") else e.dxf.text
            pos = tuple(e.dxf.insert)
            out.append({"position": pos, "text": txt,
                        "handle": e.dxf.handle})
        except Exception:
            continue
    log.info("Recovered %d engineer annotations", len(out))
    return out


# ──────────────────────────────────────────────────────────────────────────
# Live COM control (Windows + AutoCAD running) — optional
def write_live_acad(server="AutoCAD.Application", findings: list[dict] = None):
    """STUB: drives a running AutoCAD via COM. Requires comtypes on Windows."""
    try:
        import comtypes.client
    except ImportError:
        raise RuntimeError("Live COM control requires Windows + comtypes + AutoCAD.")
    acad = comtypes.client.GetActiveObject(server)
    doc  = acad.ActiveDocument
    # ...full implementation outside scope; here for users on Windows.
    return doc
