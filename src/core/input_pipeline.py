"""
INPUT PIPELINE — End-to-End PDF to NFPA 72 Coverage
=====================================================
يربط البوابة، مستخلص الجدران، مستخلص الرموز، ومستخلص الأبعاد
في مسار واحد ينتهي عند محرك حسابات NFPA 72.

كل مخرج يُوسم بمستوى ثقته.
لا يمرر أي شيء للمحرك قبل التحقق من صلاحية الرسم.

Author: The Consultant Who Refused to Lie
"""

import os
import math
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass, field
from enum import Enum

from parsers import (
    ParserConfidence,
    GateDecision,
    evaluate_drawing,
    extract_walls_from_pdf,
    extract_symbols_from_pdf,
    extract_dimensions_from_pdf,
    WallElement,
    SymbolElement,
    SymbolType,
    DimensionElement
)


class PipelineStatus(Enum):
    REJECTED = "REJECTED"
    CAUTION = "CAUTION"
    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"


@dataclass
class RoomSpec:
    """مواصفات الغرفة للمحرك."""
    points: List[Tuple[float, float]]
    area_m2: float
    confidence: str  # CERTAIN, HIGH, MODERATE


@dataclass
class DetectorSpec:
    """مواصفات الكاشف للمحرك."""
    position: Tuple[float, float]
    detector_type: str  # "smoke", "heat"
    confidence: str


@dataclass
class PipelineResult:
    """النتيجة الكاملة لأنبوب المدخلات."""
    status: PipelineStatus
    message: str
    drawing_score: float = 0.0
    walls: List[WallElement] = field(default_factory=list)
    symbols: List[SymbolElement] = field(default_factory=list)
    dimensions: List[DimensionElement] = field(default_factory=list)
    rooms: List[RoomSpec] = field(default_factory=list)
    detectors: List[DetectorSpec] = field(default_factory=list)
    ceiling_height_m: float = 3.0  # افتراضي
    requires_pe_review: bool = True
    errors: List[str] = field(default_factory=list)


class InputPipeline:
    """
    المسار الكامل: PDF → تقرير جاهز للمحرك.

    خطواته:
    1. تقييم الرسم (Confidence Gate)
    2. إن كان مرفوضاً، توقف فوراً
    3. استخلاص الجدران
    4. استخلاص الرموز (كواشف)
    5. استخلاص الأبعاد (لتحديد مقياس الرسم والمساحات)
    6. بناء Room و Detectors
    7. إخراج PipelineResult
    """

    def __init__(self, pdf_path: str):
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"Drawing not found: {pdf_path}")
        self.pdf_path = pdf_path
        self.errors: List[str] = []

    def execute(self) -> PipelineResult:
        """تنفيذ المسار الكامل."""
        # ── المرحلة 1: البوابة ──
        confidence = evaluate_drawing(self.pdf_path)
        if confidence.gate == GateDecision.REJECT:
            return PipelineResult(
                status=PipelineStatus.REJECTED,
                message=confidence.message,
                drawing_score=confidence.score,
                requires_pe_review=True,
                errors=[confidence.message]
            )

        # ── المرحلة 2: الاستخلاص ──
        walls = extract_walls_from_pdf(self.pdf_path)
        symbols = extract_symbols_from_pdf(self.pdf_path)
        dimensions = extract_dimensions_from_pdf(self.pdf_path)

        # ── المرحلة 3: بناء الغرف ──
        rooms = self._build_rooms(walls, dimensions)

        # ── المرحلة 4: بناء الكواشف ──
        detectors = self._build_detectors(symbols, dimensions)

        # ── المرحلة 5: استخراج ارتفاع السقف ──
        ceiling_height = self._extract_ceiling_height(dimensions)

        # ── المرحلة 6: تحديد الحالة النهائية ──
        status = PipelineStatus.HIGH_CONFIDENCE
        if confidence.gate == GateDecision.CAUTION:
            status = PipelineStatus.CAUTION

        # PE REVIEW مطلوب دائماً حتى V&V على 50 مشروع
        requires_pe = True

        # تحقق من وجود أخطاء صامتة
        if not walls:
            self.errors.append("NO_WALLS: Could not extract any walls from drawing")
        if not symbols:
            self.errors.append("NO_SYMBOLS: Could not extract any fire protection symbols")
        if not dimensions:
            self.errors.append("NO_DIMENSIONS: Could not extract any dimensions")

        message = self._build_message(status, confidence.score, walls, symbols, dimensions)

        return PipelineResult(
            status=status,
            message=message,
            drawing_score=confidence.score,
            walls=walls,
            symbols=symbols,
            dimensions=dimensions,
            rooms=rooms,
            detectors=detectors,
            ceiling_height_m=ceiling_height,
            requires_pe_review=requires_pe,
            errors=self.errors
        )

    def _build_rooms(self, walls: List[WallElement], dims: List[DimensionElement]) -> List[RoomSpec]:
        """بناء RoomSpec من الجدران المستخلصة."""
        rooms = []
        for wall in walls:
            if len(wall.geometry) < 3:
                continue
            # حساب المساحة التقريبية من إحداثيات الجدار
            area = self._polygon_area(wall.geometry)
            # تحويل المساحة باستخدام أول بُعد موجود (تقريبي)
            scale_factor = 1.0
            if dims:
                # نفترض أن البُعد الأول يمثل مقياس الرسم
                scale_factor = dims[0].value_m / max(
                    abs(wall.geometry[1][0] - wall.geometry[0][0]),
                    0.01
                )
            rooms.append(RoomSpec(
                points=wall.geometry,
                area_m2=round(area * scale_factor * scale_factor, 2),
                confidence=wall.confidence.value
            ))
        return rooms

    def _build_detectors(self, symbols: List[SymbolElement], dims: List[DimensionElement]) -> List[DetectorSpec]:
        """بناء DetectorSpec من الرموز المستخلصة."""
        detectors = []
        for sym in symbols:
            center_x = (sym.bbox[0] + sym.bbox[2]) / 2
            center_y = (sym.bbox[1] + sym.bbox[3]) / 2

            if sym.symbol_type == SymbolType.HEAT_DETECTOR:
                det_type = "heat"
            else:
                det_type = "smoke"

            detectors.append(DetectorSpec(
                position=(center_x, center_y),
                detector_type=det_type,
                confidence=sym.confidence.value
            ))
        return detectors

    def _extract_ceiling_height(self, dims: List[DimensionElement]) -> float:
        """محاولة استخراج ارتفاع السقف من الأبعاد."""
        # بسيط: نبحث عن أصغر بُعد رأسي (غالباً ارتفاع)
        if not dims:
            return 3.0
        # نفترض أن الأبعاد الأصغر قد تكون الارتفاع
        heights = [d.value_m for d in dims if d.value_m <= 5.0]
        if heights:
            return min(heights)
        return 3.0

    def _polygon_area(self, points: List[Tuple[float, float]]) -> float:
        """حساب مساحة مضلع باستخدام صيغة shoelace."""
        n = len(points)
        if n < 3:
            return 0.0
        area = 0.0
        for i in range(n):
            x1, y1 = points[i]
            x2, y2 = points[(i + 1) % n]
            area += x1 * y2 - x2 * y1
        return abs(area) / 2.0

    def _build_message(self, status: PipelineStatus, score: float,
                       walls: List, symbols: List, dims: List) -> str:
        """بناء رسالة ملخصة."""
        return (
            f"Pipeline {status.value}. "
            f"Score: {score:.2f}. "
            f"Walls: {len(walls)}, Symbols: {len(symbols)}, Dims: {len(dims)}. "
            f"PE REVIEW REQUIRED."
        )


def process_drawing(pdf_path: str) -> PipelineResult:
    """دالة مساعدة سريعة."""
    pipeline = InputPipeline(pdf_path)
    return pipeline.execute()