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
            # Special handling for Raster PDFs with decent completeness
            # Only allow if: has scale bar OR has explicit dimensions
            is_raster = file_details.get('type') in ['raster', 'mixed']
            has_completeness = comp_details.get('scale_found') or comp_details.get('legend_found')
            has_scale = comp_details.get('scale_found') is True  # Text mentions scale
            
            if is_raster and has_completeness and has_scale and final >= 0.5:
                # First try standard text extraction
                from src.core.dimension_extractor import extract_scale_from_pdf
                actual_scale = extract_scale_from_pdf(self.pdf_path)
                scale_confidence = 0.95 if actual_scale else 0.0
                
                # If standard extraction fails, try CV (raster enhancer)
                if not actual_scale:
                    try:
                        from src.core.scale_bar_detector import detect_scale_bar
                        cv_result = detect_scale_bar(self.pdf_path)
                        if cv_result.found and cv_result.meters_per_unit:
                            actual_scale = cv_result.meters_per_unit
                            scale_confidence = cv_result.confidence  # CV confidence
                            has_scale = True
                    except Exception as e:
                        scale_confidence = 0.0
                
                if not actual_scale:
                    # Try RasterEnhancer as last resort
                    try:
                        from src.core.raster_enhancer import enhance_raster
                        enh_result = enhance_raster(self.pdf_path)
                        if enh_result.success and enh_result.scale_estimate:
                            actual_scale = enh_result.scale_estimate
                            scale_confidence = enh_result.confidence
                            has_scale = True
                    except Exception as e:
                        scale_confidence = 0.0
                
                # Try reverse scale estimation if nothing found
                if not actual_scale:
                    try:
                        from src.core.reverse_scale_estimator import estimate_reverse_scale
                        reverse_result = estimate_reverse_scale(self.pdf_path)
                        if reverse_result.found and reverse_result.meters_per_unit:
                            actual_scale = reverse_result.meters_per_unit
                            scale_confidence = reverse_result.confidence
                            has_scale = True
                    except Exception as e:
                        pass
                
                CRITICAL_SAFETY_THRESHOLD = 0.95
                
                if not actual_scale:
                    # No scale found - REJECT
                    gate = GateDecision.REJECT
                    message = (
                        f"REJECT: No scale detected in raster PDF. "
                        f"CV + reverse estimation attempted. "
                        f"Provide vector PDF or verified scale bar."
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
                    f"REJECT: Raster drawing without scale bar. "
                    f"Cannot extract meaningful measurements. "
                    f"Provide vector PDF or PDF with scale bar."
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