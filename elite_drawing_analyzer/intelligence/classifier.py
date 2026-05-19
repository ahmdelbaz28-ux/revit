"""
intelligence/classifier.py
==========================
Symbol classifier. Three layers of intelligence — used in order:

  1. EXACT MATCH        — block name / IFC type / layer name → catalogue lookup
                          (deterministic, confidence 1.0)
  2. EMBEDDING MATCH    — visual embedding (ORB/HOG or CLIP if available) →
                          k-NN against KB examples.
  3. RULE/HEURISTIC     — geometric heuristics (circle in circle = sprinkler,
                          camera-shape, etc.) as last-resort.

Every classification writes a row to `decisions` so the system can learn from
human corrections later.

Designed so you can plug in a deep model later (CLIP, DINO, custom CNN) without
touching anything else — just implement `Embedder` interface.
"""
from __future__ import annotations
import io, logging, re
from dataclasses import dataclass
from typing import Optional, Protocol

import cv2
import numpy as np

from .knowledge_base import KnowledgeBase

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────
class Embedder(Protocol):
    dim: int
    def embed(self, img_bgr: np.ndarray) -> np.ndarray: ...


class HOGEmbedder:
    """Classical, zero-dependency, fast. Good baseline for symbols."""
    dim = 1764  # default HOG output for 64×64 with default params
    def __init__(self):
        self.hog = cv2.HOGDescriptor(_winSize=(64,64), _blockSize=(16,16),
                                     _blockStride=(8,8), _cellSize=(8,8), _nbins=9)
    def embed(self, img_bgr: np.ndarray) -> np.ndarray:
        if img_bgr.ndim == 3:
            g = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        else:
            g = img_bgr
        g = cv2.resize(g, (64,64), interpolation=cv2.INTER_AREA)
        v = self.hog.compute(g).flatten().astype(np.float32)
        n = np.linalg.norm(v) or 1.0
        return v / n


@dataclass
class Classification:
    symbol: str
    confidence: float
    reasoning: str           # human-readable trace
    decision_id: Optional[int] = None


# ──────────────────────────────────────────────────────────────────────────
class SymbolClassifier:
    """Composable classifier — exact → embedding → heuristic."""

    # Block-name patterns that are dead-giveaways
    NAME_PATTERNS = {
        "smoke_detector":    re.compile(r"\b(smoke|smk|sd|smoke[\-_ ]?det)\b", re.I),
        "heat_detector":     re.compile(r"\b(heat|hd|heat[\-_ ]?det)\b", re.I),
        "sprinkler_pendant": re.compile(r"\b(sprink|spk|pendant)\b", re.I),
        "manual_call_point": re.compile(r"\b(mcp|manual[\-_ ]?call|pull[\-_ ]?stn?)\b", re.I),
        "exit_sign":         re.compile(r"\b(exit)\b", re.I),
        "emergency_light":   re.compile(r"\b(emerg|em[\-_ ]?light|exit[\-_ ]?light)\b", re.I),
        "camera_dome":       re.compile(r"\b(cam[\-_ ]?dome|dome[\-_ ]?cam|cctv[\-_ ]?dome)\b", re.I),
        "camera_bullet":     re.compile(r"\b(bullet|cctv|ipcam|cam[\-_ ]?\d+)\b", re.I),
        "pir_sensor":        re.compile(r"\b(pir|motion[\-_ ]?det)\b", re.I),
        "access_reader":     re.compile(r"\b(access|reader|prox)\b", re.I),
        "fire_extinguisher": re.compile(r"\b(fe|extg|extinguisher)\b", re.I),
        "light_fixture":     re.compile(r"\b(light|lum|luminaire|fixture)\b", re.I),
        "socket_outlet":     re.compile(r"\b(socket|outlet|recep)\b", re.I),
        "distribution_board":re.compile(r"\b(db|panel|distribution)\b", re.I),
        "cable_tray":        re.compile(r"\b(tray|ladder)\b", re.I),
        "hvac_diffuser":     re.compile(r"\b(diffuser|grille|vav)\b", re.I),
        "pipe_chw":          re.compile(r"\b(chw|chilled)\b", re.I),
    }

    def __init__(self, kb: KnowledgeBase, embedder: Optional[Embedder] = None):
        self.kb = kb
        self.embedder = embedder or HOGEmbedder()
        self._cached_examples = None  # (names list, matrix Nxd)

    # ── refresh embedding index from KB
    def _refresh_index(self):
        rows = self.kb.fetch_all_embeddings()
        if not rows:
            self._cached_examples = ([], np.zeros((0, self.embedder.dim), np.float32))
            return
        names = []
        mats  = []
        for name, emb_bytes, conf in rows:
            v = np.frombuffer(emb_bytes, dtype=np.float32)
            if v.shape[0] != self.embedder.dim: continue
            names.append(name)
            mats.append(v)
        self._cached_examples = (names, np.vstack(mats) if mats else np.zeros((0, self.embedder.dim), np.float32))

    # ── public API
    def classify_by_name(self, name: str) -> Optional[Classification]:
        if not name: return None
        for sym, patt in self.NAME_PATTERNS.items():
            if patt.search(name):
                return Classification(sym, 0.95, f"name pattern match: '{name}' → {sym}")
        # also try exact symbol name in KB
        if self.kb.get_symbol(name.lower()):
            return Classification(name.lower(), 1.0, f"exact KB hit: {name}")
        return None

    def classify_by_image(self, img_bgr: np.ndarray,
                          k: int = 5, accept_thr: float = 0.72) -> Optional[Classification]:
        if self._cached_examples is None:
            self._refresh_index()
        names, mat = self._cached_examples
        if len(names) == 0:
            return None
        q = self.embedder.embed(img_bgr)
        # cosine similarity (vectors are L2-normalized)
        sims = mat @ q
        top = np.argsort(-sims)[:k]
        # weighted vote
        votes: dict[str,float] = {}
        for i in top:
            votes[names[i]] = votes.get(names[i], 0.0) + float(sims[i])
        best_name, best_score = max(votes.items(), key=lambda kv: kv[1])
        norm = best_score / sum(votes.values())
        if best_score / k < accept_thr:
            return None
        return Classification(best_name, float(min(0.99, norm)),
                              f"embedding k-NN: top-{k} weighted vote = {best_name}")

    def classify_by_heuristic(self, img_bgr: np.ndarray) -> Optional[Classification]:
        """Very conservative geometric fallbacks. Better to return None than guess."""
        if img_bgr is None or img_bgr.size == 0: return None
        g = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY) if img_bgr.ndim==3 else img_bgr
        circles = cv2.HoughCircles(g, cv2.HOUGH_GRADIENT, dp=1.2, minDist=10,
                                   param1=120, param2=20, minRadius=3, maxRadius=60)
        n_circ = 0 if circles is None else circles.shape[1]
        if n_circ >= 2:
            return Classification("sprinkler_pendant", 0.55,
                                  f"heuristic: {n_circ} concentric circles → likely sprinkler")
        if n_circ == 1:
            return Classification("smoke_detector", 0.45,
                                  "heuristic: single circle → maybe smoke detector (LOW confidence)")
        return None

    def classify(self,
                 img_bgr: Optional[np.ndarray] = None,
                 block_name: Optional[str] = None,
                 layer_name: Optional[str] = None,
                 file_sha: str = "",
                 page: int = 0,
                 bbox: tuple = (0,0,0,0)) -> Classification:
        # 1) exact
        for cand in (block_name, layer_name):
            r = self.classify_by_name(cand) if cand else None
            if r:
                r.decision_id = self.kb.record_decision(file_sha, page, bbox, r.symbol, r.confidence)
                return r
        # 2) embedding
        if img_bgr is not None:
            r = self.classify_by_image(img_bgr)
            if r:
                r.decision_id = self.kb.record_decision(file_sha, page, bbox, r.symbol, r.confidence)
                return r
        # 3) heuristic
        if img_bgr is not None:
            r = self.classify_by_heuristic(img_bgr)
            if r:
                r.decision_id = self.kb.record_decision(file_sha, page, bbox, r.symbol, r.confidence)
                return r
        # 4) unknown — be honest
        r = Classification("unknown", 0.0, "no method produced a confident answer")
        r.decision_id = self.kb.record_decision(file_sha, page, bbox, r.symbol, r.confidence)
        return r

    # ── learning hook
    def learn_from(self, img_bgr: np.ndarray, symbol_name: str,
                   file_sha: str, bbox: tuple, confidence: float = 1.0):
        """Add a labelled example to the KB and invalidate cache."""
        v = self.embedder.embed(img_bgr).astype(np.float32)
        ok, png = cv2.imencode(".png", img_bgr)
        self.kb.add_example(symbol_name, v.tobytes(), file_sha, bbox,
                            confidence=confidence,
                            image_bytes=png.tobytes() if ok else None)
        self._cached_examples = None  # force refresh
