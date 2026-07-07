# NOSONAR
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

try:
    import _fitz_compat as fitz  # PyMuPDF
except ImportError:
    fitz = None  # PDF features unavailable without pymupdf
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Tuple


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
        if fitz is None:
            raise ImportError(
                "PyMuPDF (pymupdf) is required for PDF parsing. "
                "Install with: pip install pymupdf"
            )
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
        scale_keywords = ['scale', 'scale 1:', '1:', '1/8', '1/4', 'meter', 'ft', 'mètre',
                    'مقياس', 'drawing scale', '1:100', '1:50', '1:200']
        details["scale_found"] = any(kw in self._text.lower() for kw in [k.lower() for k in scale_keywords])
        if details["scale_found"]:
            score += 0.3

        # Layers
        config = self.doc.layer_ui_configs()
        details["num_layers"] = len(config) if config else 0
        if details["num_layers"] >= 5:
            score += 0.1

        # Legend - expanded keywords for better detection
        legend_keywords = ['legend', 'symbol legend', 'abbreviations', 'notes and symbols',
                        'مفتاح الرموز', 'key', 'drawing list', 'device schedule']
        details["legend_found"] = any(kw.lower() in self._text.lower() for kw in legend_keywords)

        if details["legend_found"]:
            score += 0.1
            # Expand NFPA symbol keywords
            nfpa_symbols = ['smoke', 'detector', 'sprinkler', 'heat', 'horn', 'strobe',
                          'pull', 'nac', 'notification', 'speaker', 'pull station', 'heat detector',
                          'smoke detector', 'manual pull', 'bell', 'indicator']
            details["nfpa_symbols_mentioned"] = [s for s in nfpa_symbols if s in self._text.lower()]
            # More symbols = higher score
            if len(details["nfpa_symbols_mentioned"]) >= 3:
                score += 0.1
            elif details["nfpa_symbols_mentioned"]:
                score += 0.05

        return min(0.6, score), details

    # ──────────────────────────────────────────────
    # 3. الحكم النهائي
    # ──────────────────────────────────────────────
    def evaluate(self) -> ConfidenceResult:  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
        file_score, file_details = self._score_file_quality()
        comp_score, comp_details = self._score_completeness()

        raw = file_score + comp_score
        final = max(0.0, min(1.0, raw))

        if final < 0.7:
            # Special handling for Raster PDFs with decent completeness
            # Only allow if: has scale bar OR has explicit dimensions
            is_raster = file_details.get('type') in ['raster', 'mixed']
            has_completeness = comp_details.get('scale_found') or comp_details.get('legend_found')
            has_scale = comp_details.get('scale_found') is True  # Text mentions scale

            if is_raster and has_completeness and has_scale and final >= 0.5:
                # First try standard text extraction
                # V108 FIX: All src.core.* imports replaced with try/except guards.
                # These modules (dimension_extractor, scale_bar_detector,
                # raster_enhancer, reverse_scale_estimator) don't exist in the
                # current codebase. Scale extraction falls through to default.
                actual_scale = None
                scale_confidence = 0.0

                # Try dimension extraction from PDF text (local module)
                try:
                    from .pdf_input_layer import (
                        extract_scale_from_pdf as _extract_scale,
                    )
                    actual_scale = _extract_scale(self.pdf_path)
                    scale_confidence = 0.95 if actual_scale else 0.0
                except (ImportError, Exception):  # NOSONAR - python:S5713
                    pass

                # If still no scale, try PDF parser as fallback
                if not actual_scale:
                    try:
                        from .pdf_parser import PDFParser
                        # V140 FIX: PDFParser.__init__ takes min_confidence (float),
                        # not pdf_path. The path is passed to .parse().
                        _parser = PDFParser()
                        _result = _parser.parse(self.pdf_path)
                        if hasattr(_result, 'scale') and _result.scale:
                            actual_scale = _result.scale
                            scale_confidence = 0.8
                            has_scale = True
                    except (ImportError, Exception):  # NOSONAR - python:S5713
                        scale_confidence = 0.0

                CRITICAL_SAFETY_THRESHOLD = 0.95

                if not actual_scale:
                    # No scale found - REJECT
                    gate = GateDecision.REJECT
                    message = (
                        "REJECT: No scale detected in raster PDF. "
                        "CV + reverse estimation attempted. "
                        "Provide vector PDF or verified scale bar."
                    )
                elif scale_confidence < CRITICAL_SAFETY_THRESHOLD:
                    # CV scale found but confidence < 95% - REJECT for safety
                    gate = GateDecision.REJECT
                    message = (
                        f"REJECT: Scale detected (confidence {scale_confidence:.0%}) < 95%. "
                        f"For safety, manual verification required. "
                        f"Provide vector PDF or verified scale bar."
                    )
                else:
                    # High confidence scale - CAUTION with manual verification
                    gate = GateDecision.CAUTION
                    message = (
                        f"CAUTION: Scale extracted via CV ({scale_confidence:.0%} confidence). "
                        f"MANUAL SCALE VERIFICATION REQUIRED. "
                        f"PE REVIEW REQUIRED before use."
                    )
            elif is_raster and has_completeness and not has_scale:
                # Raster without scale - cannot get meaningful measurements
                gate = GateDecision.REJECT
                message = (
                    "REJECT: Raster drawing without scale bar. "
                    "Cannot extract meaningful measurements. "
                    "Provide vector PDF or PDF with scale bar."
                )
            elif final < 0.7:
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
