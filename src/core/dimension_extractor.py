"""
DIMENSION EXTRACTOR — Measurement Extraction
=============================================
يقرأ الأبعاد من نصوص PDF (مثل "12.5 m" أو "40 ft").
يحول إلى متر. ثقة HIGH إن كان النص واضحاً، وإلا MODERATE.

Author: The Consultant Who Refused to Lie
"""

import fitz
import re
import os
from typing import List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class ConfidenceLevel(Enum):
    CERTAIN = "CERTAIN"
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    UNACCEPTABLE = "UNACCEPTABLE"


@dataclass
class DimensionElement:
    value_m: float           # القيمة بالمتر
    original_text: str       # النص الأصلي
    bbox: Tuple[float, float, float, float]
    confidence: ConfidenceLevel
    raw: dict = None
    
    def to_dict(self) -> dict:
        return {
            "value_m": self.value_m,
            "original_text": self.original_text,
            "bbox": self.bbox,
            "confidence": self.confidence.value
        }


class DimensionExtractor:
    """يبحث عن نصوص تشبه الأبعاد ويحولها إلى متر."""

    # نمط يطابق رقم + وحدة (m, cm, mm, ft, inch, ') - مع أو بدون فراغ
    DIM_PATTERN = re.compile(
        r'(\d+(?:\.\d+)?)\s*(m|cm|mm|ft|feet|in|inch|\'|")',
        re.IGNORECASE
    )

    # عوامل التحويل إلى متر
    UNIT_TO_M = {
        'm': 1.0,
        'cm': 0.01,
        'mm': 0.001,
        'ft': 0.3048,
        'feet': 0.3048,
        'in': 0.0254,
        'inch': 0.0254,
        "'": 0.3048,
        '"': 0.0254,
    }

    def __init__(self, pdf_path: str, page_number: int = 0):
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"File not found: {pdf_path}")
        self.pdf_path = pdf_path
        self.doc = fitz.open(pdf_path)
        if page_number >= len(self.doc):
            raise ValueError(f"Page {page_number} not found")
        self.page = self.doc[page_number]

    def extract_dimensions(self) -> List[DimensionElement]:
        """استخراج جميع الأبعاد من النصوص."""
        words = self.page.get_text("words")
        dims = []
        
        # ابحث في كل كلمة
        for i, word in enumerate(words):
            text = word[4].strip()
            match = self.DIM_PATTERN.search(text)
            if match:
                value = float(match.group(1))
                unit = match.group(2).lower()
                if unit in self.UNIT_TO_M:
                    value_m = value * self.UNIT_TO_M[unit]
                    # إذا النص واضح (ليس ضمن فوضى) نعطيه HIGH، وإلا MODERATE
                    conf = ConfidenceLevel.HIGH if len(text) < 15 else ConfidenceLevel.MODERATE
                    dims.append(DimensionElement(
                        value_m=round(value_m, 4),
                        original_text=text,
                        bbox=(word[0], word[1], word[2], word[3]),
                        confidence=conf,
                        raw={"word": word, "unit": unit}
                    ))
            else:
                # تحقق إذا كانت الوحدة منفصلة عن الرقم (مثل "3.5" + "m")
                if i > 0:
                    prev_text = words[i-1][4].strip()
                    curr_text = text.lower()
                    # لو previous كان رقم والحالي وحدة
                    if re.match(r'^\d+\.?\d*$', prev_text) and curr_text in self.UNIT_TO_M:
                        value = float(prev_text)
                        value_m = value * self.UNIT_TO_M[curr_text]
                        conf = ConfidenceLevel.MODERATE  # وحدات منفصلة = MODERATE
                        dims.append(DimensionElement(
                            value_m=round(value_m, 4),
                            original_text=prev_text + " " + curr_text,
                            bbox=(words[i-1][0], words[i-1][1], word[2], word[3]),
                            confidence=conf,
                            raw={"unit_word": curr_text, "number_word": prev_text}
                        ))
        
        self.doc.close()
        return dims


def extract_dimensions_from_pdf(pdf_path: str, page: int = 0) -> List[DimensionElement]:
    """Extract dimensions from PDF."""
    return DimensionExtractor(pdf_path, page).extract_dimensions()