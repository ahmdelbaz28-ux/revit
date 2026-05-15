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
    
    # نمط يطابق scale bar مثل "3/32"=1'-0'" أو "1/4" = 1'-0""
    SCALE_PATTERN = re.compile(
        r'(\d+/\d+)\s*[=\"]?\s*=\s*(\d+)\'([-]?\d*)"?\s*(?:=|\')',
        re.IGNORECASE
    )
    
    # نمط بديل للـ scale
    SCALE_PATTERN2 = re.compile(
        r'(\d+/\d+)["\']?\s*=\s*(\d+)[\'-](\d*)',
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


def extract_scale_from_pdf(pdf_path: str, page: int = 0) -> float:
    """
    استخراج المقياس من الرسم البياني.
    
    Returns:
        meters_per_pdf_unit: how many real meters equals 1 PDF unit.
        None if not found.
        
    Example:
        "3/32"=1'-0'" -> 3/32 inch on drawing = 1 foot = 12 inches in reality
        -> scale = 12 / (3/32) = 128 inches per PDF unit
        -> 128 * 0.0254 = 3.2512 meters per PDF unit
    """
    try:
        doc = fitz.open(pdf_path)
        page = doc[page]
        text = page.get_text("text")
        
        # Search for scale patterns like "3/32"=1'-0'" or "1/4" = 1'-0"
        import re
        pattern = r'(\d+/\d+)["\']?\s*[=:]\s*(\d+)[\'-]?(\d*)["\']?'
        for match in re.finditer(pattern, text, re.IGNORECASE):
            fraction = match.group(1)  # e.g., "3/32"
            real_feet = int(match.group(2))
            real_inch = int(match.group(3)) if match.group(3) else 0
            
            # Convert to total real inches
            real_inches_total = real_feet * 12 + real_inch
            
            # Parse fraction
            num, denom = map(float, fraction.split('/'))
            
            # Scale: (fraction inches on drawing) = (real_inches_total inches in reality)
            # => 1 PDF unit = real_inches_total / fraction inches
            pdf_inches_per_real_inch = real_inches_total / num * denom
            
            # Convert to meters
            meters_per_pdf_inch = pdf_inches_per_real_inch * 0.0254
            meters_per_pdf_unit = meters_per_pdf_inch  # Assuming 1:1 unit mapping
            
            return round(meters_per_pdf_unit, 4)
        
        doc.close()
        return None
    except Exception:
        return None