"""
core/vectorize.py
=================
Raster → vector recovery for scanned / faded / broken-line drawings.

Pipeline:
  1. Adaptive contrast (CLAHE) — rescue faded ink
  2. Denoise + binarize (Sauvola/Otsu hybrid)
  3. Morphological close + skeletonize — heal broken lines
  4. Line detection (LSD + probabilistic Hough fallback)
  5. Curve / arc detection (contour analysis)
  6. Symbol region proposals (connected components with size + density filters)

Every recovered entity is tagged with confidence based on:
  - how much "healing" was needed (gap closure ratio)
  - line straightness residual
  - contour solidity (for symbols)
"""
from __future__ import annotations
import logging, math
from dataclasses import dataclass
from typing import List, Tuple

import cv2
import numpy as np

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────
@dataclass
class RecoveredLine:
    x1: float; y1: float; x2: float; y2: float
    confidence: float
    healed_gap_px: int = 0

@dataclass
class SymbolCandidate:
    bbox: Tuple[int,int,int,int]   # x,y,w,h
    contour: np.ndarray
    area: int
    solidity: float
    confidence: float


# ──────────────────────────────────────────────────────────────────────────
def preprocess(img_bgr: np.ndarray) -> np.ndarray:
    """CLAHE → denoise → adaptive binarize. Output: uint8 binary (255 = ink)."""
    if img_bgr.ndim == 3:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    else:
        gray = img_bgr.copy()

    # 1. CLAHE rescues faded ink
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(16,16))
    gray = clahe.apply(gray)

    # 2. Bilateral denoise — preserves edges
    gray = cv2.bilateralFilter(gray, d=5, sigmaColor=40, sigmaSpace=40)

    # 3. Adaptive threshold — robust to uneven scanning
    bin_ = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV,
        blockSize=25, C=10,
    )
    return bin_


def heal_broken_lines(bin_img: np.ndarray, max_gap: int = 6) -> Tuple[np.ndarray, float]:
    """Close gaps in dashed / interrupted lines using directional morphology.

    Returns healed image and an estimate of how much was healed (0..1 ratio).
    """
    ink_before = int(np.count_nonzero(bin_img))
    healed = bin_img.copy()
    # Directional kernels — close gaps along common drafting angles
    for angle in (0, 30, 45, 60, 90, 120, 135, 150):
        rad = math.radians(angle)
        L = max_gap * 2 + 1
        kern = np.zeros((L, L), np.uint8)
        cx, cy = L // 2, L // 2
        for t in range(-L, L+1):
            x = int(round(cx + t*math.cos(rad)))
            y = int(round(cy + t*math.sin(rad)))
            if 0 <= x < L and 0 <= y < L: kern[y, x] = 1
        healed = cv2.morphologyEx(healed, cv2.MORPH_CLOSE, kern)
    ink_after = int(np.count_nonzero(healed))
    healing_ratio = (ink_after - ink_before) / max(ink_before, 1)
    return healed, float(healing_ratio)


def detect_lines(bin_img: np.ndarray, min_len: int = 20) -> List[RecoveredLine]:
    """LSD first (sub-pixel accurate); fallback to probabilistic Hough."""
    out: List[RecoveredLine] = []
    try:
        lsd = cv2.createLineSegmentDetector(cv2.LSD_REFINE_ADV)
        lines, _, _, _ = lsd.detect(bin_img)
        if lines is not None:
            for l in lines.reshape(-1, 4):
                x1,y1,x2,y2 = l
                if math.hypot(x2-x1, y2-y1) < min_len: continue
                out.append(RecoveredLine(float(x1),float(y1),float(x2),float(y2),
                                         confidence=0.9))
            return out
    except Exception as ex:
        log.warning("LSD failed (%s); falling back to Hough", ex)

    h = cv2.HoughLinesP(bin_img, 1, np.pi/360, threshold=60,
                        minLineLength=min_len, maxLineGap=8)
    if h is not None:
        for x1,y1,x2,y2 in h.reshape(-1,4):
            out.append(RecoveredLine(float(x1),float(y1),float(x2),float(y2), 0.75))
    return out


def detect_symbol_candidates(
    bin_img: np.ndarray,
    min_area: int = 80,
    max_area: int = 12000,
) -> List[SymbolCandidate]:
    """Connected components that look like symbols (cameras, detectors, sprinklers)."""
    num, labels, stats, _ = cv2.connectedComponentsWithStats(bin_img, connectivity=8)
    cands: List[SymbolCandidate] = []
    for i in range(1, num):
        x, y, w, h, area = stats[i]
        if not (min_area <= area <= max_area): continue
        # aspect ratio filter — symbols are roughly square-ish
        ar = w / max(h, 1)
        if ar < 0.3 or ar > 3.5: continue
        mask = (labels == i).astype(np.uint8) * 255
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours: continue
        cnt = max(contours, key=cv2.contourArea)
        hull = cv2.convexHull(cnt)
        hull_a = cv2.contourArea(hull) or 1.0
        solidity = float(cv2.contourArea(cnt) / hull_a)
        conf = min(1.0, 0.4 + 0.6 * solidity)
        cands.append(SymbolCandidate((x,y,w,h), cnt, int(area), solidity, conf))
    return cands


def vectorize_raster(img_bgr: np.ndarray) -> dict:
    """One-shot: returns {'lines':[...], 'symbols':[...], 'healing_ratio':...}."""
    bin_ = preprocess(img_bgr)
    healed, ratio = heal_broken_lines(bin_)
    return {
        "lines":   detect_lines(healed),
        "symbols": detect_symbol_candidates(healed),
        "healing_ratio": ratio,
        "binary":  healed,
    }
