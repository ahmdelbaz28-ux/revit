"""
intelligence/clip_embedder.py
=============================
Optional CLIP-based embedder. Drop-in replacement for HOGEmbedder.

Why: HOG works for clean schematic symbols but fails on photo-realistic
icons, faded ones, or rotated variants. CLIP embeddings handle these.

Activates only if `open_clip_torch` (or `clip`) is installed. Otherwise the
classifier falls back to HOG transparently.

Usage:
    from elite_drawing_analyzer.intelligence.classifier import SymbolClassifier
    from elite_drawing_analyzer.intelligence.clip_embedder import CLIPEmbedder

    clf = SymbolClassifier(kb, embedder=CLIPEmbedder())
"""
from __future__ import annotations
import logging
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)


class CLIPEmbedder:
    dim: int = 512  # ViT-B/32 default

    def __init__(self, model_name: str = "ViT-B-32", pretrained: str = "openai"):
        try:
            import torch, open_clip
        except ImportError as ex:
            raise RuntimeError(
                "CLIPEmbedder needs torch + open_clip_torch. "
                "Install: pip install torch open_clip_torch  "
                f"(reason: {ex})")
        self.torch = torch
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained=pretrained)
        self.model.eval()
        with torch.no_grad():
            # discover dim
            from PIL import Image
            dummy = Image.new("RGB", (64,64), (255,255,255))
            v = self.model.encode_image(self.preprocess(dummy).unsqueeze(0))
            self.dim = int(v.shape[-1])
        log.info("CLIP embedder ready: %s/%s  dim=%d", model_name, pretrained, self.dim)

    def embed(self, img_bgr: np.ndarray) -> np.ndarray:
        import cv2
        from PIL import Image
        if img_bgr.ndim == 2:
            img_bgr = cv2.cvtColor(img_bgr, cv2.COLOR_GRAY2BGR)
        rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        x = self.preprocess(pil).unsqueeze(0)
        with self.torch.no_grad():
            v = self.model.encode_image(x).cpu().numpy().flatten()
        v = v.astype(np.float32)
        n = np.linalg.norm(v) or 1.0
        return v / n
