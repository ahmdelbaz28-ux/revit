"""
PARSER CONFIDENCE — Input Gateway for NFPA 72 Engine
=====================================================
يُقيّم أي ملف PDF قبل أن يلمس المحرك.
يرفض أو يسمح. لا يحلل. فقط يحكم.

Gate decisions:
  REJECT          → لا تدخل. ارجع للمهندس.
  CAUTION         → ادخل لكن كل مخرجاتك تُوسم بـ MODERATE.
  HIGH_CONFIDENCE → ادخل. أنت جدير بالثقة المؤقتة.

Author: The Consultant Who Refused to Lie
"""

import fitz  # PyMuPDF
import os
from typing import Dict, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum


class GateDecision(Enum):
    REJECT = "REJECT"
    CAUTION = "CAUTION"
    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"


@dataclass
class ConfidenceResult:
    score: float
    gate: GateDecision
    message: str
    details: Dict = field(default_factory=dict)


class ParserConfidence:
    """
    يفتح PDF ويُقيّم مدى صلاحيته للتحليل الآلي.

    المعايير:
    1. هل الملف vector أم raster؟
    2. هل يوجد scale annotation؟
    3. هل هناك طبقات (layers) تدل على رسم احترافي؟
    4. هل توجد رموز NFPA 170 في legend؟

    القرار النهائي:
    - score < 0.7  → REJECT
    - 0.7 ≤ score < 0.85 → CAUTION
    - score ≥ 0.85 → HIGH_CONFIDENCE
    """

    def __init__(self, pdf_path: str):
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"Drawing not found: {pdf_path}")
        self.pdf_path = pdf_path
        self.doc = fitz.open(pdf_path)
        if len(self.doc) == 0:
            raise ValueError("PDF contains no pages")
        self.page = self.doc[0]
        self._text_cache: Optional[str] = None

    # ──────────────────────────────────────────────
    # 1. جودة الملف (File Quality)
    # ──────────────────────────────────────────────
    def _score_file_quality(self) -> Tuple[float, Dict]:
        score = 0.0
        details = {}

        images = self.page.get_images(full=True)
        text_blocks = self.page.get_text("blocks")
        has_vector = len(text_blocks) > 0
        has_raster = len(images) > 0

        if has_vector and not has_raster:
            score += 0.4
            details["type"] = "pure_vector"
        elif has_vector and has_raster:
            score += 0.1
            details["type"] = "mixed"
        elif has_raster and not has_vector:
            score -= 0.3
            details["type"] = "pure_raster"
        else:
            score -= 0.4
            details["type"] = "empty_or_unknown"

        if has_raster:
            xref = images[0][0]
            pix = fitz.Pixmap(self.doc, xref)
            if pix.width < 1000 or pix.height < 1000:
                score -= 0.2
                details["raster_quality"] = "low_dpi"
            else:
                details["raster_quality"] = "adequate_dpi"
        else:
            details["raster_quality"] = "n/a"

        return max(-0.5, min(0.4, score)), details

    # ──────────────────────────────────────────────
    # 2. الاكتمال الهندي (Completeness)
    # ──────────────────────────────────────────────
    @property
    def _text(self) -> str:
        if self._text_cache is None:
            self._text_cache = self.page.get_text().lower()
        return self._text_cache

    def _score_completeness(self) -> Tuple[float, Dict]:
        score = 0.0
        details = {}

        # Scale annotation
        scale_keywords = ['scale', '1:', '1/8', '1/4', 'meter', 'ft', 'mètre']
        details["scale_found"] = any(kw in self._text for kw in scale_keywords)
        if details["scale_found"]:
            score += 0.3

        # Layers
        config = self.doc.layer_ui_configs()
        details["num_layers"] = len(config) if config else 0
        if details["num_layers"] >= 5:
            score += 0.1

        # Legend
        details["legend_found"] = 'legend' in self._text
        if details["legend_found"]:
            score += 0.1
            nfpa_symbols = ['smoke', 'detector', 'sprinkler', 'heat', 'horn', 'strobe', 'pull', 'nac']
            details["nfpa_symbols_mentioned"] = [s for s in nfpa_symbols if s in self._text]
            if details["nfpa_symbols_mentioned"]:
                score += 0.1

        return min(0.6, score), details

    # ──────────────────────────────────────────────
    # 3. الحكم النهائي
    # ──────────────────────────────────────────────
    def evaluate(self) -> ConfidenceResult:
        file_score, file_details = self._score_file_quality()
        comp_score, comp_details = self._score_completeness()

        raw = file_score + comp_score
        final = max(0.0, min(1.0, raw))

        if final < 0.7:
            gate = GateDecision.REJECT
            message = (
                f"REJECT: Drawing score {final:.2f} < 0.7. "
                f"Unfit for automated analysis. Engineer must review manually."
            )
        elif final < 0.85:
            gate = GateDecision.CAUTION
            message = (
                f"CAUTION: Drawing score {final:.2f}. "
                f"Analysis allowed but all outputs marked MODERATE. PE REVIEW REQUIRED."
            )
        else:
            gate = GateDecision.HIGH_CONFIDENCE
            message = (
                f"HIGH CONFIDENCE: Drawing score {final:.2f}. "
                f"Suitable for automated processing."
            )

        self.doc.close()
        return ConfidenceResult(
            score=round(final, 3),
            gate=gate,
            message=message,
            details={
                "file_quality": file_details,
                "completeness": comp_details,
                "raw_score": round(raw, 3),
            }
        )


# ──────────────────────────────────────────────────
# دالة مساعدة للاستخدام المباشر
# ──────────────────────────────────────────────────
def evaluate_drawing(pdf_path: str) -> ConfidenceResult:
    """تقييم سريع لرسم PDF قبل إدخاله للمحرك."""
    parser = ParserConfidence(pdf_path)
    return parser.evaluate()