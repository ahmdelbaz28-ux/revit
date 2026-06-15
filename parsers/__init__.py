"""
Parsers Package - Input Layer for NFPA 72 Engine
=================================================
Contains:
- ParserConfidence: evaluates drawing suitability for automated analysis
- GeometryExtractor: extracts closed walls from PDF vector
- SymbolExtractor: extracts protection symbols from PDF text

GRACEFUL DEGRADATION:
  PDF-related modules (ParserConfidence, GeometryExtractor, SymbolExtractor)
  require PyMuPDF (pymupdf). If pymupdf is not installed, these modules
  are set to None and PDF features are unavailable. DXF/DWG parsing via
  DWGParser and DXFParser still works (they only need ezdxf + _path_security).
  This ensures the core safety-critical pipeline is never blocked by an
  optional PDF dependency.
"""

# PDF-dependent modules — wrapped in try/except so that missing pymupdf
# does NOT prevent importing the parsers package entirely. DWG/DXF parsing
# does NOT require pymupdf.

try:
    from .parser_confidence import (
        ConfidenceResult,
        GateDecision,
        ParserConfidence,
        evaluate_drawing,
    )
except ImportError:
    ParserConfidence = None
    ConfidenceResult = None
    GateDecision = None
    evaluate_drawing = None

try:
    from .geometry_extractor import ConfidenceLevel as GeometryConfidence
    from .geometry_extractor import (
        GeometryExtractor,
        WallElement,
        extract_walls_from_pdf,
    )
except ImportError:
    GeometryExtractor = None
    WallElement = None
    GeometryConfidence = None
    extract_walls_from_pdf = None

# SymbolExtractor — local parser module (no src.core fallback)
try:
    from .symbol_extractor import (
        SymbolElement,
        SymbolExtractor,
        SymbolType,
        extract_symbols_from_pdf,
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
