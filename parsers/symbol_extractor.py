"""
SYMBOL EXTRACTOR — Fire Protection Symbols Detection
=====================================================
يستخلص مواقع الرموز من نصوص PDF (labels) فقط.
لا يستخدم رؤية حاسوبية. كل رمز مستخلص يُوسم بـ MODERATE
ويجب أن يراجعه مهندس.

Author: The Consultant Who Refused to Lie
"""

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Tuple

import _fitz_compat as fitz


class SymbolType(Enum):
    """NFPA 170 device types."""

    SMOKE_DETECTOR = "SMOKE_DETECTOR"
    HEAT_DETECTOR = "HEAT_DETECTOR"
    PULL_STATION = "PULL_STATION"
    HORN_STROBE = "HORN_STROBE"
    SPEAKER = "SPEAKER"
    STROBE = "STROBE"
    HORN = "HORN"
    NAC_PANEL = "NAC_PANEL"
    FIRE_ALARM_PANEL = "FIRE_ALARM_PANEL"
    SPRINKLER = "SPRINKLER"
    FLOW_SWITCH = "FLOW_SWITCH"
    UNKNOWN = "UNKNOWN"


class ConfidenceLevel(Enum):
    """مستويات الثقة."""

    CERTAIN = "CERTAIN"
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    UNACCEPTABLE = "UNACCEPTABLE"


@dataclass
class SymbolElement:
    """رمز مستخلص من الرسم."""

    symbol_type: SymbolType
    bbox: Tuple[float, float, float, float]  # x0,y0,x1,y1
    confidence: ConfidenceLevel
    text: str
    page: int = 0
    raw: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "type": self.symbol_type.value,
            "bbox": self.bbox,
            "confidence": self.confidence.value,
            "text": self.text,
            "page": self.page
        }


class SymbolExtractor:
    """
    يقرأ نصوص PDF بحثاً عن أسماء رموز NFPA.

    USAGE:
        extractor = SymbolExtractor("drawing.pdf", 0)
        symbols = extractor.extract_symbols()

        for sym in symbols:
            print(f"{sym.symbol_type.value}: {sym.text} at {sym.bbox}")
    """

    # الكلمات المفتاحية لكل نوع رمز
    KEYWORDS = {
        SymbolType.SMOKE_DETECTOR: [
            r'\bSD\b', r'\bSMOKE\b', r'\bSMOKE\s*DETECTOR\b',
            r'\bSMOKE\s*DET\b', r'\bPHOTO\b', r'\bION\b',
            r'\bPHOTOELECTRIC\b'
        ],
        SymbolType.HEAT_DETECTOR: [
            r'\bHD\b', r'\bHEAT\b', r'\bHEAT\s*DETECTOR\b',
            r'\bTHERMAL\b', r'\bROR\b', r'\bFIXED\s*TEMP\b',
            r'\bRATE[ -]*OF[ -]*RISE\b'
        ],
        SymbolType.PULL_STATION: [
            r'\bPULL\b', r'\bPULL\s*STATION\b', r'\bMANUAL\s*PULL\b',
            r'\bMANUAL\s*STATION\b', r'\bPS\b', r'\bBREAK\s*GLASS\b'
        ],
        SymbolType.HORN_STROBE: [
            r'\bH/S\b', r'\bHORN/STROBE\b', r'\bHORN\s*STROBE\b',
            r'\bA/V\b', r'\bAV\b'
        ],
        SymbolType.HORN: [
            r'\bHORN\b', r'\bH\b'
        ],
        SymbolType.STROBE: [
            r'\bSTROBE\b', r'\bVISUAL\b'
        ],
        SymbolType.SPEAKER: [
            r'\bSPEAKER\b', r'\bSPKR\b', r'\bSP\b'
        ],
        SymbolType.NAC_PANEL: [
            r'\bNAC\b', r'\bNOTIFICATION\s*APPLIANCE\s*CIRCUIT\b'
        ],
        SymbolType.FIRE_ALARM_PANEL: [
            r'\bFACP\b', r'\bFIRE\s*ALARM\s*PANEL\b', r'\bMAIN\s*PANEL\b',
            r'\bCONTROL\s*PANEL\b', r'\bPANEL\b'
        ],
        SymbolType.SPRINKLER: [
            r'\bSPRINKLER\b', r'\bSPR\b', r'\bHEAD\b'
        ],
        SymbolType.FLOW_SWITCH: [
            r'\bFLOW\s*SWITCH\b', r'\bWATERFLOW\b'
        ],
    }

    def __init__(self, pdf_path: str, page_number: int = 0):
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"File not found: {pdf_path}")
        self.pdf_path = pdf_path
        self.doc = fitz.open(pdf_path)
        if page_number >= len(self.doc):
            raise ValueError(f"Page {page_number} not found in PDF")
        self.page = self.doc[page_number]
        self.page_number = page_number

    def extract_symbols(self) -> List[SymbolElement]:
        """استخراج جميع الرموز المحتملة من النصوص."""
        words = self.page.get_text("words")  # (x0,y0,x1,y1,text,block,line,word)
        symbols = []

        for word in words:
            text = word[4].strip()
            bbox = (word[0], word[1], word[2], word[3])

            for sym_type, patterns in self.KEYWORDS.items():
                for pat in patterns:
                    if re.search(pat, text, re.IGNORECASE):
                        symbols.append(SymbolElement(
                            symbol_type=sym_type,
                            bbox=bbox,
                            text=text,
                            page=self.page_number,
                            raw={"word": word}
                        ))
                        break

        self.doc.close()
        return symbols

    def extract_by_type(self, symbol_type: SymbolType) -> List[SymbolElement]:
        """استخراج رموز من نوع محدد."""
        all_symbols = self.extract_symbols()
        return [s for s in all_symbols if s.symbol_type == symbol_type]

    def get_symbol_count(self) -> Dict[str, int]:
        """إحصاء الرموز المستخلصة."""
        symbols = self.extract_symbols()
        counts = {}
        for sym in symbols:
            key = sym.symbol_type.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    def close(self):
        """إغلاق المستند."""
        if self.doc:
            self.doc.close()


def extract_symbols_from_pdf(pdf_path: str, page: int = 0) -> List[SymbolElement]:
    """
    دالة مساعدة سريعة لاستخراج الرموز.

    Args:
        pdf_path: مسار ملف PDF
        page: رقم الصفحة (يبدأ من 0)

    Returns:
        List of SymbolElement objects

    """
    extractor = SymbolExtractor(pdf_path, page)
    return extractor.extract_symbols()


def extract_devices_from_pdf(pdf_path: str, page: int = 0) -> Dict[str, List[SymbolElement]]:
    """
    استخراج جميع الأجهزة من PDF وتصنيفها حسب النوع.

    Returns:
        Dict mapping SymbolType to list of symbols

    """
    symbols = extract_symbols_from_pdf(pdf_path, page)

    # Group by type
    devices = {}
    for sym in symbols:
        key = sym.symbol_type.value
        if key not in devices:
            devices[key] = []
        devices[key].append(sym)

    return devices
