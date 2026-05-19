"""
SYMBOL EXTRACTOR — Fire Protection Symbols Detection
=====================================================
يستخلص مواقع الرموز من نصوص PDF (labels) فقط.
لا يستخدم رؤية حاسوبية. كل رمز مستخلص يُوسم بـ MODERATE
ويجب أن يراجعه مهندس.

Author: The Consultant Who Refused to Lie
"""

import fitz
import re
import os
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class SymbolType(Enum):
    SMOKE_DETECTOR = "SMOKE_DETECTOR"
    HEAT_DETECTOR = "HEAT_DETECTOR"
    PULL_STATION = "PULL_STATION"
    HORN_STROBE = "HORN_STROBE"
    NAC_PANEL = "NAC_PANEL"
    FIRE_ALARM_PANEL = "FIRE_ALARM_PANEL"
    UNKNOWN = "UNKNOWN"


class ConfidenceLevel(Enum):
    CERTAIN = "CERTAIN"
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    UNACCEPTABLE = "UNACCEPTABLE"


@dataclass
class SymbolElement:
    symbol_type: SymbolType
    bbox: Tuple[float, float, float, float]  # x0,y0,x1,y1
    confidence: ConfidenceLevel
    text: str
    raw: Dict = None
    
    def to_dict(self) -> dict:
        return {
            "type": self.symbol_type.value,
            "bbox": self.bbox,
            "confidence": self.confidence.value,
            "text": self.text
        }


class SymbolExtractor:
    """يقرأ نصوص PDF بحثاً عن أسماء رموز NFPA."""

    # الكلمات المفتاحية لكل نوع رمز
    KEYWORDS = {
        SymbolType.SMOKE_DETECTOR: [
            r'\bSD\b', r'\bSMOKE\b', r'\bSMOKE\s*DETECTOR\b',
            r'\bSMOKE\s*DET\b', r'\bPHOTO\b', r'\bION\b'
        ],
        SymbolType.HEAT_DETECTOR: [
            r'\bHD\b', r'\bHEAT\b', r'\bHEAT\s*DETECTOR\b',
            r'\bTHERMAL\b', r'\bROR\b', r'\bFIXED\s*TEMP\b'
        ],
        SymbolType.PULL_STATION: [
            r'\bPULL\b', r'\bPULL\s*STATION\b', r'\bMANUAL\s*PULL\b',
            r'\bMANUAL\s*STATION\b'
        ],
        SymbolType.HORN_STROBE: [
            r'\bHORN\b', r'\bSTROBE\b', r'\bH/S\b', r'\bA/V\b',
            r'\bHORN/STROBE\b', r'\bSPEAKER\s*STROBE\b'
        ],
        SymbolType.NAC_PANEL: [
            r'\bNAC\b', r'\bNOTIFICATION\s*APPLIANCE\s*CIRCUIT\b'
        ],
        SymbolType.FIRE_ALARM_PANEL: [
            r'\bFACP\b', r'\bFIRE\s*ALARM\s*PANEL\b', r'\bMAIN\s*PANEL\b'
        ]
    }

    def __init__(self, pdf_path: str, page_number: int = 0):
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"File not found: {pdf_path}")
        self.pdf_path = pdf_path
        self.doc = fitz.open(pdf_path)
        if page_number >= len(self.doc):
            raise ValueError(f"Page {page_number} not found")
        self.page = self.doc[page_number]

    def extract_symbols(self) -> List[SymbolElement]:
        """استخراج جميع الرموز المحتملة من النصوص."""
        words = self.page.get_text("words")  # (x0,y0,x1,y1,text,block,line,word)
        symbols = []
        for word in words:
            text = word[4].strip().upper()
            bbox = (word[0], word[1], word[2], word[3])
            for sym_type, patterns in self.KEYWORDS.items():
                for pat in patterns:
                    if re.search(pat, text, re.IGNORECASE):
                        symbols.append(SymbolElement(
                            symbol_type=sym_type,
                            bbox=bbox,
                            confidence=ConfidenceLevel.MODERATE,
                            text=text,
                            raw={"word": word}
                        ))
                        break  # لا تبحث عن أنماط أخرى لنفس الكلمة
        self.doc.close()
        return symbols


def extract_symbols_from_pdf(pdf_path: str, page: int = 0) -> List[SymbolElement]:
    """Extract symbols from PDF file."""
    return SymbolExtractor(pdf_path, page).extract_symbols()