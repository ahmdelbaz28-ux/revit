"""
Parsers Package - Input Layer for NFPA 72 Engine
=================================================
Contains:
- ParserConfidence: evaluates drawing suitability for automated analysis
- GeometryExtractor: extracts closed walls from PDF vector
- SymbolExtractor: extracts protection symbols from PDF text
"""

from .parser_confidence import (
    ParserConfidence,
    ConfidenceResult,
    GateDecision,
    evaluate_drawing
)

from .geometry_extractor import (
    GeometryExtractor,
    WallElement,
    ConfidenceLevel as GeometryConfidence,
    extract_walls_from_pdf
)

# SymbolExtractor — local parser module (no src.core fallback)
try:
    from .symbol_extractor import (
        SymbolExtractor,
        SymbolElement,
        SymbolType,
        extract_symbols_from_pdf
    )
except ImportError:
    SymbolExtractor = None
    SymbolElement = None
    SymbolType = None
    extract_symbols_from_pdf = None

__all__ = [
    "ParserConfidence",
    "ConfidenceResult",
    "GateDecision",
    "evaluate_drawing",
    "GeometryExtractor",
    "WallElement",
    "extract_walls_from_pdf",
    "SymbolExtractor",
    "SymbolElement",
    "SymbolType",
    "extract_symbols_from_pdf",
]
