"""
Parsers Package - Input Layer for NFPA 72 Engine
=================================================
يحتوي على:
- ParserConfidence: يقيّم صلاحية الرسم للتحليل الآلي
- GeometryExtractor: يستخلص الجدران المغلقة من PDF vector
- SymbolExtractor: يستخلص رموز الحماية من نصوص PDF
- DimensionExtractor: يستخلص الأبعاد ويحولها إلى متر

الاستخدام:
    from parsers import ParserConfidence, GeometryExtractor
    from parsers import SymbolExtractor, DimensionExtractor
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

# SymbolExtractor - from src/core/ or parsers/
try:
    from .symbol_extractor import (
        SymbolExtractor,
        SymbolElement,
        SymbolType,
        extract_symbols_from_pdf
    )
except ImportError:
    from src.core.symbol_extractor import (
        SymbolExtractor,
        SymbolElement,
        SymbolType,
        extract_symbols_from_pdf
    )

# DimensionExtractor - same logic
try:
    from .dimension_extractor import (
        DimensionExtractor,
        DimensionElement,
        extract_dimensions_from_pdf,
        extract_scale_from_pdf,
    )
except ImportError:
    from src.core.dimension_extractor import (
        DimensionExtractor,
        DimensionElement,
        extract_dimensions_from_pdf,
        extract_scale_from_pdf,
    )

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
    "DimensionExtractor",
    "DimensionElement",
    "extract_dimensions_from_pdf",
]