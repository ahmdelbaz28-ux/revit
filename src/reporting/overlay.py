"""
reporting/overlay.py
====================
Renders findings as an annotated overlay on top of the original drawing.

Output: PNG per page with:
  • coloured boxes around each classified symbol
  • severity-coloured circles for compliance findings
  • distance lines between non-compliant pairs
  • legend strip + page summary

Colour code:
  CRITICAL = red       MAJOR = orange
  MINOR    = yellow    ADVISORY = blue
  CONFIRMED (high conf) = green box
  LOW CONF              = grey  box (needs review)
"""
from __future__ import annotations
import os, logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

log = logging.getLogger(__name__)


SEV_COLOR = {
    "critical": (0, 0, 220),
    "major":    (0, 140, 255),
    "minor":    (0, 220, 255),
    "advisory": (255, 140, 0),
    "info":     (200, 200, 200),
}
CONF_COLOR_OK    = (0, 180, 0)
CONF_COLOR_LOW   = (160, 160, 160)


def render_overlay(report, out_dir: str, raster_inputs: Optional[dict] = None) -> list[str]:
    """
    raster_inputs : dict[page_int → image_path_or_array]
                    If None, we look at the original file (PDF/image) and
                    re-rasterize. For DXF/DWG you should pre-render to PNG.
    Returns list of generated PNG paths.
    """
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    pages = _collect_page_images(report, raster_inputs)
    paths = []
    by_page_elements = _group_by_page(report.elements)
    by_page_findings = _group_findings_by_page(report.findings, report.elements)

    for pno, img in pages.items():
        canvas = img.copy()
        _draw_elements(canvas, by_page_elements.get(pno, []))
        _draw_findings(canvas, by_page_findings.get(pno, []), report.elements)
        _draw_legend(canvas, report, pno)
        p = out_dir / f"overlay_p{pno}.png"
        cv2.imwrite(str(p), canvas)
        paths.append(str(p))
        log.info("Overlay → %s", p)
    return paths


def _collect_page_images(report, raster_inputs) -> dict[int, np.ndarray]:
    if raster_inputs:
        return {int(k): (cv2.imread(v) if isinstance(v,str) else v)
                for k,v in raster_inputs.items()}
    # try to recover the rasterized side-cars made by ingest
    base = report.file
    candidates = list(Path(".").glob(f"**/{base}.p*.png"))
    out = {}
    for c in candidates:
        m = c.stem.split(".p")[-1]
        try: pno = int(m)
        except ValueError: continue
        img = cv2.imread(str(c))
        if img is not None: out[pno] = img
    if not out:
        # fall back to a blank canvas per page so overlay still works
        out[0] = np.full((1600, 2400, 3), 250, np.uint8)
    return out


def _group_by_page(elements):
    g = {}
    for el in elements:
        g.setdefault(el["page"], []).append(el)
    return g


def _group_findings_by_page(findings, elements):
    # findings carry evidence with i/j indices into elements list; we tag
    # them onto the page of the referenced element if available.
    g = {}
    for f in findings:
        page = 0
        ev = f.get("evidence") or {}
        for key in ("i","j"):
            if key in ev and 0 <= ev[key] < len(elements):
                page = elements[ev[key]]["page"]; break
        g.setdefault(page, []).append(f)
    return g


def _draw_elements(canvas, els):
    for el in els:
        x0,y0,x1,y1 = [int(v) for v in el["bbox"]]
        conf = el["classification"]["confidence"]
        sym  = el["classification"]["symbol"]
        col = CONF_COLOR_OK if conf >= 0.6 else CONF_COLOR_LOW
        cv2.rectangle(canvas, (x0,y0), (x1,y1), col, 2)
        label = f"{sym} {conf:.2f}"
        _put_label(canvas, label, (x0, max(0,y0-6)), col)


def _draw_findings(canvas, findings, all_elements):
    for f in findings:
        col = SEV_COLOR.get(f["severity"], (180,180,180))
        ev = f.get("evidence") or {}
        i, j = ev.get("i"), ev.get("j")
        if i is not None and j is not None and i < len(all_elements) and j < len(all_elements):
            a = _center(all_elements[i]["bbox"]); b = _center(all_elements[j]["bbox"])
            cv2.line(canvas, a, b, col, 2)
            mid = ((a[0]+b[0])//2, (a[1]+b[1])//2)
            cv2.circle(canvas, mid, 9, col, -1)
            if "distance_m" in ev:
                _put_label(canvas, f"{ev['distance_m']} m", mid, col)


def _draw_legend(canvas, report, pno):
    h, w = canvas.shape[:2]
    bar = 28
    cv2.rectangle(canvas, (0,0), (w, bar), (40,40,40), -1)
    txt = f"EDA  |  {report.file}  p{pno}  |  elements={len(report.elements)}  "\
          f"findings={len(report.findings)}  |  critical={sum(1 for f in report.findings if f['severity']=='critical')}"
    cv2.putText(canvas, txt, (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255,255,255), 1, cv2.LINE_AA)


def _center(bbox):
    return (int((bbox[0]+bbox[2])//2), int((bbox[1]+bbox[3])//2))


def _put_label(canvas, text, org, color):
    cv2.putText(canvas, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
