"""
knowledge/classifier.py — V8 Symbol Classifier
=========================================

V8: This classifier uses ONLY base patterns. Self-learner disabled.
- Block-name lookup against BASE_PATTERNS
- Layer-priors disabled (use pattern_library instead)
- No runtime pattern injection
- Confidence calibration disabled (use FPE-reviewed values)

Pattern Library (V8) REPLACES self_learner functionality.
"""
from __future__ import annotations
import io, logging, re
from dataclasses import dataclass
from typing import Optional, Protocol

import cv2
import numpy as np

from .memory import KnowledgeBase

log = logging.getLogger(__name__)


class Embedder(Protocol):
    dim: int
    def embed(self, img_bgr: np.ndarray) -> np.ndarray: ...


class HOGEmbedder:
    dim = 1764
    def __init__(self):
        self.hog = cv2.HOGDescriptor(_winSize=(64,64), _blockSize=(16,16),
                                     _blockStride=(8,8), _cellSize=(8,8), _nbins=9)
    def embed(self, img_bgr: np.ndarray) -> np.ndarray:
        g = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY) if img_bgr.ndim==3 else img_bgr
        g = cv2.resize(g, (64,64), interpolation=cv2.INTER_AREA)
        v = self.hog.compute(g).flatten().astype(np.float32)
        n = np.linalg.norm(v) or 1.0
        return v / n


@dataclass
class Classification:
    symbol: str
    confidence: float
    reasoning: str
    decision_id: Optional[int] = None


class SymbolClassifier:
    # Static hard-coded patterns — never lost even if KB wiped.
    # Boundary `(?:^|[\W_])` matches start-of-string OR any non-alphanumeric
    # OR underscore — critical because CAD names often use underscores
    # (e.g. "SMK_DET", "FA_SMOKE_01") and Python's \b treats _ as word-char,
    # so \bsmk\b would NEVER match inside "SMK_DET".
    BASE_PATTERNS = {
        "smoke_detector":    re.compile(r"(?:^|[\W_])(smoke|smk|sd|smoke[\-_ ]?det)(?:$|[\W_])", re.I),
        "heat_detector":     re.compile(r"(?:^|[\W_])(heat|hd|heat[\-_ ]?det)(?:$|[\W_])", re.I),
        "sprinkler_pendant": re.compile(r"(?:^|[\W_])(sprink|spk|pendant)(?:$|[\W_])", re.I),
        "manual_call_point": re.compile(r"(?:^|[\W_])(mcp|manual[\-_ ]?call|pull[\-_ ]?stn?)(?:$|[\W_])", re.I),
        "exit_sign":         re.compile(r"(?:^|[\W_])(exit)(?:$|[\W_])", re.I),
        "emergency_light":   re.compile(r"(?:^|[\W_])(emerg|em[\-_ ]?light|exit[\-_ ]?light)(?:$|[\W_])", re.I),
        "camera_dome":       re.compile(r"(?:^|[\W_])(cam[\-_ ]?dome|dome[\-_ ]?cam|cctv[\-_ ]?dome)(?:$|[\W_])", re.I),
        "camera_bullet":     re.compile(r"(?:^|[\W_])(bullet|cctv|ipcam|cam[\-_ ]?\d+)(?:$|[\W_])", re.I),
        "pir_sensor":        re.compile(r"(?:^|[\W_])(pir|motion[\-_ ]?det)(?:$|[\W_])", re.I),
        "access_reader":     re.compile(r"(?:^|[\W_])(access|reader|prox)(?:$|[\W_])", re.I),
        "fire_extinguisher": re.compile(r"(?:^|[\W_])(fe|extg|extinguisher)(?:$|[\W_])", re.I),
        "light_fixture":     re.compile(r"(?:^|[\W_])(light|lum|luminaire|fixture)(?:$|[\W_])", re.I),
        "socket_outlet":     re.compile(r"(?:^|[\W_])(socket|outlet|recep)(?:$|[\W_])", re.I),
        "distribution_board":re.compile(r"(?:^|[\W_])(db|panel|distribution)(?:$|[\W_])", re.I),
        "cable_tray":        re.compile(r"(?:^|[\W_])(tray|ladder)(?:$|[\W_])", re.I),
        "hvac_diffuser":     re.compile(r"(?:^|[\W_])(diffuser|grille|vav)(?:$|[\W_])", re.I),
        "pipe_chw":          re.compile(r"(?:^|[\W_])(chw|chilled)(?:$|[\W_])", re.I),
    }

    def __init__(self, kb: KnowledgeBase, embedder: Optional[Embedder] = None,
                 learner=None):
        self.kb = kb
        self.embedder = embedder or HOGEmbedder()
        # V8: SelfLearner disabled - use pattern_library instead
        self.learner = None  # was: learner
        self._cached_examples = None

    @classmethod
    def match_name_pattern(cls, text: str) -> Optional[str]:
        """Stateless name → symbol resolver (used by legend harvester)."""
        if not text: return None
        for sym, patt in cls.BASE_PATTERNS.items():
            if patt.search(text): return sym
        return None

    def _all_patterns(self) -> dict:
        """Return base patterns (V8: no learned patterns - use pattern_library)."""
        out = dict(self.BASE_PATTERNS)
        # V8: SelfLearner disabled - use pattern_library instead
        # if self.learner:
        #     for sym, pats in self.learner.all_learned_patterns().items():
        #         for p in pats:
        #             out.setdefault(f"{sym}_learned_{p}", re.compile(p, re.I))
        return out

    # ── name match ─
    def classify_by_name(self, name: str, *, layer: Optional[str] = None) -> Optional[Classification]:
        if not name: return None
        # V8: SelfLearner disabled - use pattern_library instead
        # if self.learner:
        #     sym = self.learner.alias_lookup(name)
        #     if sym:
        #         return Classification(sym, 0.97, f"learned alias: '{name}' → {sym}")
        # 1) pattern match (base patterns only)
        for sym, patt in self._all_patterns().items():
            if patt.search(name):
                clean_sym = sym.split("_learned_")[0]
                return Classification(clean_sym, 0.93, f"pattern match: '{name}'")
        # 2) exact symbol name in KB
        if self.kb.get_symbol(name.lower()):
            return Classification(name.lower(), 1.0, f"exact KB hit: {name}")
        # 3) layer prior - V8: disabled
        # if self.learner and layer:
        #     prior = self.learner.layer_prior(layer)
        #     if prior:
        #         sym, prob = prior
        #         return Classification(sym, float(prob*0.8),
        #                               f"layer prior: '{layer}' → {sym} (p={prob:.2f})")
        return None

    # ── image / embedding ─
    def _refresh_index(self):
        rows = self.kb.fetch_all_embeddings()
        if not rows:
            self._cached_examples = ([], np.zeros((0, self.embedder.dim), np.float32))
            return
        names, mats = [], []
        for name, emb_bytes, conf in rows:
            v = np.frombuffer(emb_bytes, dtype=np.float32)
            if v.shape[0] != self.embedder.dim: continue
            names.append(name); mats.append(v)
        self._cached_examples = (names,
            np.vstack(mats) if mats else np.zeros((0, self.embedder.dim), np.float32))

    def classify_by_image(self, img_bgr, k=5, accept_thr=0.72) -> Optional[Classification]:
        if self._cached_examples is None: self._refresh_index()
        names, mat = self._cached_examples
        if len(names) == 0: return None
        q = self.embedder.embed(img_bgr)
        sims = mat @ q
        top = np.argsort(-sims)[:k]
        votes = {}
        for i in top:
            votes[names[i]] = votes.get(names[i], 0.0) + float(sims[i])
        if not votes: return None
        best_name, best_score = max(votes.items(), key=lambda kv: kv[1])
        if best_score / k < accept_thr: return None
        return Classification(best_name, float(min(0.99, best_score/sum(votes.values()))),
                              f"embedding k-NN: top-{k} vote = {best_name}")

    def classify_by_heuristic(self, img_bgr):
        if img_bgr is None or img_bgr.size == 0: return None
        g = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY) if img_bgr.ndim==3 else img_bgr
        circles = cv2.HoughCircles(g, cv2.HOUGH_GRADIENT, dp=1.2, minDist=10,
                                   param1=120, param2=20, minRadius=3, maxRadius=60)
        n_circ = 0 if circles is None else circles.shape[1]
        if n_circ >= 2:
            return Classification("sprinkler_pendant", 0.55,
                                  f"heuristic: {n_circ} concentric circles")
        if n_circ == 1:
            return Classification("smoke_detector", 0.45,
                                  "heuristic: single circle (LOW confidence)")
        return None

    def classify(self, img_bgr=None, block_name=None, layer_name=None,
                 file_sha="", page=0, bbox=(0,0,0,0)) -> Classification:
        for cand in (block_name, layer_name):
            r = self.classify_by_name(cand, layer=layer_name) if cand else None
            if r:
                r.confidence = self._calibrate(r.confidence)
                r.decision_id = self.kb.record_decision(file_sha, page, bbox,
                                                       r.symbol, r.confidence)
                return r
        if img_bgr is not None:
            r = self.classify_by_image(img_bgr) or self.classify_by_heuristic(img_bgr)
            if r:
                r.confidence = self._calibrate(r.confidence)
                r.decision_id = self.kb.record_decision(file_sha, page, bbox,
                                                       r.symbol, r.confidence)
                return r
        r = Classification("unknown", 0.0, "no method produced a confident answer")
        r.decision_id = self.kb.record_decision(file_sha, page, bbox, "unknown", 0.0)
        return r

    def _calibrate(self, raw: float) -> float:
        # V8: SelfLearner disabled - return raw confidence
        # if self.learner:
        #     return self.learner.calibrated_confidence(raw)
        return raw

    def learn_from(self, img_bgr, symbol_name, file_sha, bbox, confidence=1.0):
        v = self.embedder.embed(img_bgr).astype(np.float32)
        ok, png = cv2.imencode(".png", img_bgr)
        self.kb.add_example(symbol_name, v.tobytes(), file_sha, bbox,
                            confidence=confidence,
                            image_bytes=png.tobytes() if ok else None)
        self._cached_examples = None
