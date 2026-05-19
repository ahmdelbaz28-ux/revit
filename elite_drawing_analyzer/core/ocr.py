"""
core/ocr.py
===========
Hybrid OCR for legends / schedules / tags / room names.

Strategy:
  - Use pytesseract by default (free, decent for engineering drawings).
  - Optionally accept an EasyOCR or PaddleOCR backend (drop-in).
  - Always pre-process: deskew, upscale, binarize — drawings are tiny text.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import List, Optional

import cv2
import numpy as np

log = logging.getLogger(__name__)


@dataclass
class OCRBox:
    text: str
    bbox: tuple   # (x,y,w,h)
    confidence: float


def _deskew(gray: np.ndarray) -> np.ndarray:
    coords = np.column_stack(np.where(gray > 0))
    if coords.size == 0: return gray
    angle = cv2.minAreaRect(coords)[-1]
    angle = -(90 + angle) if angle < -45 else -angle
    if abs(angle) < 0.5: return gray
    h, w = gray.shape[:2]
    M = cv2.getRotationMatrix2D((w/2, h/2), angle, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def preprocess_for_ocr(img_bgr: np.ndarray, upscale: float = 2.0) -> np.ndarray:
    if img_bgr.ndim == 3:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    else:
        gray = img_bgr
    gray = cv2.resize(gray, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.bilateralFilter(gray, 5, 30, 30)
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    bw = _deskew(255 - bw)
    return 255 - bw


def run_ocr(img_bgr: np.ndarray, backend: str = "tesseract", lang: str = "eng+ara") -> List[OCRBox]:
    pre = preprocess_for_ocr(img_bgr)
    if backend == "tesseract":
        return _ocr_tesseract(pre, lang)
    if backend == "easyocr":
        return _ocr_easyocr(pre, lang)
    raise ValueError(f"Unknown OCR backend: {backend}")


def _ocr_tesseract(bin_img: np.ndarray, lang: str) -> List[OCRBox]:
    try:
        import pytesseract
        from pytesseract import Output
    except ImportError:
        log.warning("pytesseract not installed — OCR disabled. pip install pytesseract & apt install tesseract-ocr")
        return []
    data = pytesseract.image_to_data(bin_img, lang=lang, output_type=Output.DICT,
                                     config="--psm 11 --oem 1")
    out = []
    for i, txt in enumerate(data["text"]):
        if not txt or not txt.strip(): continue
        conf = float(data["conf"][i] or 0)
        if conf < 30: continue
        out.append(OCRBox(text=txt.strip(),
                          bbox=(data["left"][i], data["top"][i],
                                data["width"][i], data["height"][i]),
                          confidence=conf/100.0))
    return out


def _ocr_easyocr(bin_img: np.ndarray, lang: str) -> List[OCRBox]:
    try:
        import easyocr
    except ImportError:
        log.warning("easyocr not installed"); return []
    reader = easyocr.Reader(lang.replace("+",",").split(","), gpu=False, verbose=False)
    res = reader.readtext(bin_img)
    out = []
    for (poly, txt, conf) in res:
        xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
        out.append(OCRBox(text=txt.strip(),
                          bbox=(int(min(xs)), int(min(ys)),
                                int(max(xs)-min(xs)), int(max(ys)-min(ys))),
                          confidence=float(conf)))
    return out
