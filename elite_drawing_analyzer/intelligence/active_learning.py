"""
intelligence/active_learning.py
===============================
Closes the feedback loop.

Workflow:
  1. analyze_file() writes decisions into the KB with confidences.
  2. `review_pending()` returns the lowest-confidence decisions for a human.
  3. The human (or UI) calls `submit_feedback()` to confirm/correct each.
  4. Confirmed corrections immediately train the embedder index — next file
     uses them.
"""
from __future__ import annotations
import json, logging
from typing import Optional

import cv2
import numpy as np

from .knowledge_base import KnowledgeBase
from .classifier import SymbolClassifier

log = logging.getLogger(__name__)


def review_pending(kb: KnowledgeBase,
                   limit: int = 20,
                   max_confidence: float = 0.6,
                   file_sha: Optional[str] = None) -> list[dict]:
    """Return decisions awaiting human verification, lowest-confidence first."""
    q = """SELECT id, file_sha, page, bbox, predicted_symbol, confidence, ts
           FROM decisions
           WHERE confirmed IS NULL AND confidence < ?
           {extra}
           ORDER BY confidence ASC LIMIT ?"""
    extra = "AND file_sha = ?" if file_sha else ""
    args  = [max_confidence] + ([file_sha, limit] if file_sha else [limit])
    rows = kb.conn.execute(q.format(extra=extra), args).fetchall()
    return [dict(r) for r in rows]


def submit_feedback(kb: KnowledgeBase, decision_id: int,
                    is_correct: bool, correction: Optional[str] = None,
                    crop_image_path: Optional[str] = None) -> dict:
    """Confirm or correct one decision. If a crop is provided AND we learn a
    new label, add it to the embedding index so future runs improve."""
    row = kb.conn.execute("SELECT * FROM decisions WHERE id=?", (decision_id,)).fetchone()
    if not row:
        raise ValueError(f"No decision {decision_id}")
    row = dict(row)

    final_label = row["predicted_symbol"] if is_correct else correction
    if not is_correct and not correction:
        raise ValueError("correction symbol name required when is_correct=False")

    kb.confirm(decision_id, is_correct, correction=correction)

    # Active learning step: feed the labelled crop back
    if crop_image_path and final_label and final_label != "unknown":
        img = cv2.imread(crop_image_path)
        if img is not None:
            clf = SymbolClassifier(kb)
            bbox = tuple(json.loads(row["bbox"]) if isinstance(row["bbox"], str) else row["bbox"])
            clf.learn_from(img, final_label, row["file_sha"], bbox, confidence=1.0)
            log.info("Learned new example for '%s'", final_label)

    return {"decision_id": decision_id, "is_correct": is_correct,
            "final_label": final_label}


def metrics(kb: KnowledgeBase) -> dict:
    """Performance metrics derived from feedback so far."""
    c = kb.conn.execute
    total      = c("SELECT COUNT(*) FROM decisions WHERE confirmed IS NOT NULL").fetchone()[0]
    confirmed  = c("SELECT COUNT(*) FROM decisions WHERE confirmed=1").fetchone()[0]
    corrected  = c("SELECT COUNT(*) FROM decisions WHERE confirmed=0").fetchone()[0]
    accuracy   = (confirmed / total) if total else None
    # accuracy stratified by predicted confidence bucket
    buckets = {}
    for lo, hi in [(0.0,0.4),(0.4,0.6),(0.6,0.8),(0.8,1.01)]:
        t = c("SELECT COUNT(*) FROM decisions WHERE confirmed IS NOT NULL AND confidence>=? AND confidence<?",
              (lo, hi)).fetchone()[0]
        ok= c("SELECT COUNT(*) FROM decisions WHERE confirmed=1 AND confidence>=? AND confidence<?",
              (lo, hi)).fetchone()[0]
        buckets[f"{lo:.1f}-{hi:.2f}"] = {"total":t, "correct":ok,
                                         "accuracy": (ok/t) if t else None}
    return {"total_judged": total, "confirmed": confirmed, "corrected": corrected,
            "accuracy": accuracy, "by_confidence_bucket": buckets}
