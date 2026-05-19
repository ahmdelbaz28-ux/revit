"""
pipeline.py
===========
End-to-end orchestration: file in → Report out.

This is the brain. It chains:

  ingest → vectorize (if raster) → ocr → classify → group → reconcile → audit

Designed for safety: every decision carries confidence, every low-confidence
finding is flagged for human review. No silent assumptions.

Usage:
    from elite_drawing_analyzer.pipeline import analyze_file
    report = analyze_file("/path/to/drawing.pdf")
    report.print_summary()
    report.save_json("/tmp/report.json")
"""
from __future__ import annotations
import json, logging, os, time
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from .core.ingest import ingest, NormalizedDrawing, Entity
from .core.vectorize import vectorize_raster
from .core.ocr import run_ocr
from .intelligence.knowledge_base import KnowledgeBase
from .intelligence.classifier import SymbolClassifier, Classification
from .reasoning.compliance import ComplianceEngine, Finding
from .reasoning.schedule_match import reconcile, ScheduleLine
from .reporting.overlay import render_overlay
from .reporting.html_report import generate_report_html

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────
@dataclass
class ElementResult:
    page: int
    bbox: tuple
    classification: dict        # asdict(Classification)
    layer: Optional[str] = None
    block: Optional[str] = None
    attributes: dict = field(default_factory=dict)


@dataclass
class Report:
    file: str
    file_type: str
    file_sha: str
    summary: dict
    elements: list = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    findings: list = field(default_factory=list)            # compliance findings
    reconciliation: list = field(default_factory=list)      # schedule vs drawing
    ocr_texts: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    elapsed_seconds: float = 0.0

    # ── output helpers ──
    def save_json(self, path: str):
        Path(path).write_text(json.dumps(asdict(self), indent=2, default=str))
        return path

    def print_summary(self):
        print(f"\n{'='*72}\nFILE: {self.file}  ({self.file_type})\n{'='*72}")
        print(f"SHA-256: {self.file_sha}")
        print(f"Elapsed: {self.elapsed_seconds:.1f}s\n")
        print("Summary:"); print(json.dumps(self.summary, indent=2))
        print("\nClassified counts:"); print(json.dumps(self.counts, indent=2))
        if self.findings:
            print(f"\n⚠️  COMPLIANCE FINDINGS  ({len(self.findings)}):")
            for f in self.findings:
                print(f"  [{f['severity'].upper():8}] {f['code']} {f['rule']}: {f['message']}")
                if f.get("recommendation"):
                    print(f"           ↳ {f['recommendation']}")
        if self.reconciliation:
            print(f"\n📋 SCHEDULE RECONCILIATION  ({len(self.reconciliation)}):")
            for r in self.reconciliation:
                print(f"  [{r['status']:18}] {r['item']:25} sched={r['scheduled_qty']:>4}  "
                      f"actual={r['actual_qty']:>4}  Δ={r['delta']:+d}")
        if self.warnings:
            print("\nWarnings:")
            for w in self.warnings: print(f"  • {w}")


# ──────────────────────────────────────────────────────────────────────────
def analyze_file(path: str,
                 kb: Optional[KnowledgeBase] = None,
                 schedule: Optional[list[dict]] = None,
                 auto_schedule: bool = True,
                 units_to_m: float = 0.001,
                 raster_dpi: int = 200,
                 do_ocr: bool = True,
                 overlay_dir: Optional[str] = None,
                 html_out: Optional[str] = None) -> Report:
    """
    Parameters
    ----------
    path        : input file (DXF/DWG/PDF/IFC/image)
    kb          : KnowledgeBase instance (uses default location if None)
    schedule    : optional list of {"item": str, "qty": int} for reconciliation
    units_to_m  : multiplier from drawing units to metres (mm → 0.001)
    raster_dpi  : DPI when rasterizing PDF pages or images for vision
    do_ocr      : run OCR on raster pages (off for speed)
    """
    t0 = time.time()
    kb = kb or KnowledgeBase()
    classifier = SymbolClassifier(kb)

    nd = ingest(path)
    kb.record_file(nd.source_sha256, nd.source_path, nd.file_type, nd.metadata)

    elements: list[ElementResult] = []
    warnings: list[str] = []
    ocr_texts: list[dict] = []

    # ── (A) Classify vector block references directly
    for e in nd.entities:
        if e.kind == "block_ref":
            cls = classifier.classify(
                img_bgr=None,
                block_name=e.block, layer_name=e.layer,
                file_sha=nd.source_sha256, page=e.page, bbox=e.bbox or (0,0,0,0),
            )
            elements.append(ElementResult(
                page=e.page, bbox=e.bbox or (0,0,0,0),
                classification=asdict(cls),
                layer=e.layer, block=e.block, attributes=e.attributes,
            ))
        elif e.kind == "text":
            ocr_texts.append({"page": e.page, "text": e.text, "from": "vector"})

    # ── (B) For IFC: products are already typed; classify by IFC class + name
    if nd.file_type == "ifc":
        for e in nd.entities:
            name = e.attributes.get("name") or ""
            ifc_type = e.kind
            cls = classifier.classify_by_name(name) or classifier.classify_by_name(ifc_type) \
                  or Classification("unknown", 0.0, f"IFC type {ifc_type} unmapped")
            cls.decision_id = kb.record_decision(nd.source_sha256, 0, (0,0,0,0),
                                                 cls.symbol, cls.confidence)
            elements.append(ElementResult(0, (0,0,0,0), asdict(cls),
                                          layer=ifc_type, block=name,
                                          attributes=e.attributes))

    # ── (C) Raster analysis for PDF pages / image files
    raster_blobs = [b for b in nd.raw_unknown if "image" in b]
    for blob in raster_blobs:
        img_path = blob["image"]; page_no = blob.get("raster_page", 0)
        img = cv2.imread(img_path)
        if img is None:
            warnings.append(f"Could not read rasterized image: {img_path}"); continue

        vres = vectorize_raster(img)
        if vres["healing_ratio"] > 0.15:
            warnings.append(
                f"Page {page_no}: significant line-healing applied "
                f"(+{vres['healing_ratio']*100:.0f}% ink). Verify recovered geometry.")

        # OCR for legends / room names / tags
        if do_ocr:
            try:
                boxes = run_ocr(img)
                for b in boxes:
                    ocr_texts.append({"page": page_no, "text": b.text,
                                      "bbox": b.bbox, "conf": b.confidence,
                                      "from": "ocr"})
            except Exception as ex:
                warnings.append(f"OCR failed on page {page_no}: {ex}")

        # Classify symbol candidates
        for cand in vres["symbols"]:
            x,y,w,h = cand.bbox
            pad = 4
            x0,y0 = max(0,x-pad), max(0,y-pad)
            x1,y1 = min(img.shape[1], x+w+pad), min(img.shape[0], y+h+pad)
            crop = img[y0:y1, x0:x1]
            if crop.size == 0: continue
            cls = classifier.classify(
                img_bgr=crop, file_sha=nd.source_sha256, page=page_no,
                bbox=(x0,y0,x1,y1),
            )
            # Honest scoring: combine classifier conf with shape conf
            cls.confidence = round(cls.confidence * cand.confidence, 3)
            elements.append(ElementResult(
                page=page_no, bbox=(x0,y0,x1,y1),
                classification=asdict(cls),
                layer=f"raster_p{page_no}",
            ))

    # ── (D) Aggregate counts
    counts = Counter(el.classification["symbol"] for el in elements
                     if el.classification["confidence"] >= 0.4)
    low_conf = sum(1 for el in elements if el.classification["confidence"] < 0.4)
    if low_conf:
        warnings.append(
            f"{low_conf} element(s) classified with confidence < 40% — "
            f"these are EXCLUDED from counts and require human review.")

    # ── (E) Compliance checks (best-effort; needs spatial info)
    findings: list[Finding] = []
    eng = ComplianceEngine(kb, units_to_m=units_to_m)
    # group positions per symbol from confident elements
    positions = defaultdict(list)
    for el in elements:
        sym = el.classification["symbol"]
        if el.classification["confidence"] < 0.5: continue
        cx = (el.bbox[0]+el.bbox[2])/2
        cy = (el.bbox[1]+el.bbox[3])/2
        positions[sym].append((cx, cy))
    if positions.get("smoke_detector"):
        findings += eng.check_detector_spacing("smoke_detector", positions["smoke_detector"])
    if positions.get("heat_detector"):
        findings += eng.check_detector_spacing("heat_detector",  positions["heat_detector"])
    if positions.get("sprinkler_pendant") or positions.get("sprinkler_upright"):
        pts = positions.get("sprinkler_pendant", []) + positions.get("sprinkler_upright", [])
        findings += eng.check_sprinkler_spacing(pts)

    # ── (F) Schedule reconciliation
    recon = []
    if schedule is None and auto_schedule and nd.file_type == "pdf":
        try:
            from .core.tables import extract_schedule_from_pdf
            schedule = extract_schedule_from_pdf(path)
            if schedule:
                warnings.append(f"Auto-extracted {len(schedule)} schedule rows from PDF.")
        except Exception as ex:
            warnings.append(f"Auto-schedule extraction failed: {ex}")
    if schedule:
        sl = [ScheduleLine(item=row["item"], qty=int(row["qty"]), raw=row) for row in schedule]
        recon = reconcile(sl, dict(counts))

    report = Report(
        file=os.path.basename(path),
        file_type=nd.file_type,
        file_sha=nd.source_sha256,
        summary=nd.summary(),
        elements=[asdict(el) for el in elements],
        counts=dict(counts),
        findings=[asdict(f) for f in findings],
        reconciliation=[asdict(r) for r in recon],
        ocr_texts=ocr_texts,
        warnings=warnings,
        elapsed_seconds=round(time.time()-t0, 2),
    )

    # ── (G) Visual artefacts
    overlay_paths = []
    if overlay_dir:
        try:
            raster_inputs = {b.get("raster_page",0): b["image"] for b in raster_blobs if "image" in b}
            overlay_paths = render_overlay(report, overlay_dir,
                                           raster_inputs=raster_inputs or None)
        except Exception as ex:
            warnings.append(f"Overlay generation failed: {ex}")
    if html_out:
        try:
            generate_report_html(report, overlay_paths=overlay_paths, out_path=html_out)
        except Exception as ex:
            warnings.append(f"HTML report failed: {ex}")

    return report


# ──────────────────────────────────────────────────────────────────────────
# Active-learning helper — call this from a UI when a user corrects something
def teach(kb: KnowledgeBase, image_path: str, symbol_name: str,
          file_sha: str = "", bbox: tuple = (0,0,0,0)):
    """Add a labelled example so the classifier improves next time."""
    img = cv2.imread(image_path)
    if img is None:
        raise RuntimeError(f"Cannot read {image_path}")
    clf = SymbolClassifier(kb)
    clf.learn_from(img, symbol_name, file_sha, bbox, confidence=1.0)
    return kb.stats()
