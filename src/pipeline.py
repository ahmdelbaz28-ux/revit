"""
pipeline.py — Unified FireSafetyGenius pipeline v1.0
====================================================

Single entry-point that wires:
  ingest → vectorize → ocr → tables → classify → reasoning → compliance
        → reconcile → safety_gates → digital_twin → smoke_sim
        → reporting → SELF-LEARNING (automatic, every file)

Key change vs v0.2: the pipeline ALWAYS calls SelfLearner.learn_from_file()
at the end. No human action required. The system genuinely improves on
every drawing it sees.
"""
from __future__ import annotations
import json, logging, os, time
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from .kernel.ingest      import ingest
from .kernel.vectorize   import vectorize_raster
from .kernel.ocr         import run_ocr
from .knowledge.memory   import KnowledgeBase
from .knowledge.classifier      import SymbolClassifier, Classification
from .knowledge.self_learner    import SelfLearner, LearningOutcome
from .reasoning.compliance      import ComplianceEngine, Finding
from .reasoning.schedule_match  import reconcile, ScheduleLine
from .reasoning.chain_of_thought import FireSafetyReasoner
from .reporting.overlay      import render_overlay
from .reporting.html_report  import generate_report_html

log = logging.getLogger(__name__)


@dataclass
class ElementResult:
    page: int
    bbox: tuple
    classification: dict
    layer: Optional[str] = None
    block: Optional[str] = None
    attributes: dict = field(default_factory=dict)


@dataclass
class Report:
    file: str
    file_type: str
    file_sha: str
    summary: dict
    elements:        list = field(default_factory=list)
    counts:          dict = field(default_factory=dict)
    findings:        list = field(default_factory=list)
    reconciliation:  list = field(default_factory=list)
    ocr_texts:       list = field(default_factory=list)
    warnings:        list = field(default_factory=list)
    learning_outcome: dict = field(default_factory=dict)
    reasoning_trace:  dict = field(default_factory=dict)
    elapsed_seconds: float = 0.0

    def save_json(self, path):
        Path(path).write_text(json.dumps(asdict(self), indent=2, default=str))
        return path

    def print_summary(self):
        print(f"\n{'='*72}\nFILE: {self.file}  ({self.file_type})\n{'='*72}")
        print(f"SHA: {self.file_sha}")
        print(f"Elapsed: {self.elapsed_seconds:.1f}s")
        print(f"\nClassified counts:"); print(json.dumps(self.counts, indent=2))
        if self.findings:
            print(f"\n⚠️  COMPLIANCE  ({len(self.findings)}):")
            for f in self.findings:
                print(f"  [{f['severity']:8}] {f['code']} {f['rule']}: {f['message']}")
        if self.reconciliation:
            print(f"\n📋 RECONCILIATION ({len(self.reconciliation)}):")
            for r in self.reconciliation:
                print(f"  [{r['status']:18}] {r['item']:25} sched={r['scheduled_qty']:>4}  "
                      f"actual={r['actual_qty']:>4}  Δ={r['delta']:+d}")
        if self.learning_outcome:
            print(f"\n🧠 LEARNING (auto): " + self.learning_outcome.get("summary",""))
        if self.reasoning_trace:
            print(f"\n🎯 VERDICT: {self.reasoning_trace.get('conclusion','')}")
        if self.warnings:
            print("\nWarnings:")
            for w in self.warnings: print(f"  • {w}")


# ──────────────────────────────────────────────────────────────────────────
def analyze_file(path: str,
                 kb: Optional[KnowledgeBase] = None,
                 schedule: Optional[list[dict]] = None,
                 auto_schedule: bool = True,
                 units_to_m: float = 0.001,
                 do_ocr: bool = True,
                 twin = None,                                   # DigitalTwin
                 do_reasoning: bool = True,
                 do_self_learn: bool = True,
                 overlay_dir: Optional[str] = None,
                 html_out: Optional[str] = None) -> Report:
    t0 = time.time()
    kb = kb or KnowledgeBase()
    learner = SelfLearner(kb)
    classifier = SymbolClassifier(kb, learner=learner)

    nd = ingest(path)
    kb.record_file(nd.source_sha256, nd.source_path, nd.file_type, nd.metadata)

    elements: list[ElementResult] = []
    warnings: list[str] = []
    ocr_texts: list[dict] = []

    # (A) vector block references
    for e in nd.entities:
        if e.kind == "block_ref":
            cls = classifier.classify(block_name=e.block, layer_name=e.layer,
                                      file_sha=nd.source_sha256, page=e.page,
                                      bbox=e.bbox or (0,0,0,0))
            elements.append(ElementResult(e.page, e.bbox or (0,0,0,0),
                                          asdict(cls), e.layer, e.block, e.attributes))
        elif e.kind == "text":
            ocr_texts.append({"page": e.page, "text": e.text, "from":"vector"})

    # (B) IFC products
    if nd.file_type == "ifc":
        for e in nd.entities:
            name = e.attributes.get("name") or ""
            cls = (classifier.classify_by_name(name) or
                   classifier.classify_by_name(e.kind) or
                   Classification("unknown", 0.0, f"IFC {e.kind} unmapped"))
            cls.decision_id = kb.record_decision(nd.source_sha256, 0, (0,0,0,0),
                                                  cls.symbol, cls.confidence)
            elements.append(ElementResult(0, (0,0,0,0), asdict(cls),
                                          e.kind, name, e.attributes))

    # (C) raster pages
    raster_blobs = [b for b in nd.raw_unknown if "image" in b]
    for blob in raster_blobs:
        page_no = blob.get("raster_page", 0)
        img = cv2.imread(blob["image"])
        if img is None: warnings.append(f"unreadable raster: {blob['image']}"); continue
        vres = vectorize_raster(img)
        if vres["healing_ratio"] > 0.15:
            warnings.append(f"Page {page_no}: heavy line-healing applied "
                            f"(+{vres['healing_ratio']*100:.0f}%). Verify.")
        if do_ocr:
            try:
                for b in run_ocr(img):
                    ocr_texts.append({"page": page_no, "text": b.text,
                                      "bbox": b.bbox, "conf": b.confidence, "from":"ocr"})
            except Exception as ex:
                warnings.append(f"OCR failed p{page_no}: {ex}")
        for cand in vres["symbols"]:
            x,y,w,h = cand.bbox; pad = 4
            x0,y0 = max(0,x-pad), max(0,y-pad)
            x1,y1 = min(img.shape[1], x+w+pad), min(img.shape[0], y+h+pad)
            crop = img[y0:y1, x0:x1]
            if crop.size == 0: continue
            cls = classifier.classify(img_bgr=crop, file_sha=nd.source_sha256,
                                      page=page_no, bbox=(x0,y0,x1,y1))
            cls.confidence = round(cls.confidence * cand.confidence, 3)
            elements.append(ElementResult(page_no, (x0,y0,x1,y1),
                                          asdict(cls), f"raster_p{page_no}"))

    # (D) counts
    counts = Counter(el.classification["symbol"] for el in elements
                     if el.classification["confidence"] >= 0.4)
    low_conf = sum(1 for el in elements if el.classification["confidence"] < 0.4)
    if low_conf:
        warnings.append(f"{low_conf} element(s) below 40% confidence — excluded "
                        f"from counts, awaiting review.")

    # (E) compliance
    findings = []
    eng = ComplianceEngine(kb, units_to_m=units_to_m)
    positions = defaultdict(list)
    for el in elements:
        if el.classification["confidence"] < 0.5: continue
        cx = (el.bbox[0]+el.bbox[2])/2
        cy = (el.bbox[1]+el.bbox[3])/2
        positions[el.classification["symbol"]].append((cx, cy))
    if positions.get("smoke_detector"):
        findings += eng.check_detector_spacing("smoke_detector", positions["smoke_detector"])
    if positions.get("heat_detector"):
        findings += eng.check_detector_spacing("heat_detector",  positions["heat_detector"])
    spr = positions.get("sprinkler_pendant",[]) + positions.get("sprinkler_upright",[])
    if spr:
        findings += eng.check_sprinkler_spacing(spr)

    # (F) auto-schedule + reconcile
    recon = []
    if schedule is None and auto_schedule and nd.file_type == "pdf":
        try:
            from .kernel.tables import extract_schedule_from_pdf
            schedule = extract_schedule_from_pdf(path)
            if schedule:
                warnings.append(f"Auto-extracted {len(schedule)} schedule rows.")
        except Exception as ex:
            warnings.append(f"Auto-schedule failed: {ex}")
    if schedule:
        sl = [ScheduleLine(item=r["item"], qty=int(r["qty"]), raw=r) for r in schedule]
        recon = reconcile(sl, dict(counts))

    # build Report
    report = Report(
        file=os.path.basename(path), file_type=nd.file_type,
        file_sha=nd.source_sha256, summary=nd.summary(),
        elements=[asdict(el) for el in elements],
        counts=dict(counts),
        findings=[asdict(f) for f in findings],
        reconciliation=[asdict(r) for r in recon],
        ocr_texts=ocr_texts, warnings=warnings,
        elapsed_seconds=round(time.time()-t0, 2),
    )

    # (G) chain-of-thought reasoning
    if do_reasoning:
        try:
            reasoner = FireSafetyReasoner(kb, classifier, twin=twin)
            trace = reasoner.evaluate_floor(report, units_to_m=units_to_m)
            report.reasoning_trace = asdict(trace)
        except Exception as ex:
            warnings.append(f"Reasoning failed: {ex}")

    # (H) AUTOMATIC SELF-LEARNING — runs every file, no human needed
    if do_self_learn:
        try:
            outcome = learner.learn_from_file(report, nd, classifier)
            report.learning_outcome = {**outcome.__dict__, "summary": outcome.summary()}
        except Exception as ex:
            warnings.append(f"Self-learning step failed: {ex}")

    # (I) visual artefacts
    overlays = []
    if overlay_dir:
        try:
            raster_inputs = {b.get("raster_page",0): b["image"] for b in raster_blobs if "image" in b}
            overlays = render_overlay(report, overlay_dir, raster_inputs=raster_inputs or None)
        except Exception as ex:
            warnings.append(f"Overlay failed: {ex}")
    if html_out:
        try:
            generate_report_html(report, overlay_paths=overlays, out_path=html_out)
        except Exception as ex:
            warnings.append(f"HTML failed: {ex}")

    return report
