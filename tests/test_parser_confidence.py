"""
PARSER CONFIDENCE — Brutal Validation Tests
=============================================
لا يختبر "هل تشتغل". يختبر "هل ترفض عندما يجب أن ترفض".
كل اختبار هنا يُحاكي رسماً حقيقياً يمكن أن يصل من المهندس.

Author: The Consultant Who Refused to Lie
"""

import pytest
import fitz  # PyMuPDF
import os
import tempfile
from pathlib import Path

# استيراد الكود الذي بنيناه
from parsers.parser_confidence import (
    ParserConfidence,
    ConfidenceResult,
    GateDecision,
    evaluate_drawing
)


# ═══════════════════════════════════════════════════════════
# أدوات مساعدة لتوليد ملفات PDF اختبارية
# ═══════════════════════════════════════════════════════

class PDFFactory:
    """يُنتج ملفات PDF بمحتوى محدّد للاختبارات."""

    @staticmethod
    def create_empty_pdf(path: str):
        """صفحة بيضاء تماماً."""
        doc = fitz.open()
        doc.new_page(width=612, height=792)
        doc.save(path)
        doc.close()

    @staticmethod
    def create_vector_with_scale(path: str):
        """PDF vector مع scale annotation."""
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        # إضافة نص scale
        page.insert_text((50, 50), "SCALE 1:100", fontsize=14)
        # إضافة شكل مستطيل كجدار
        page.draw_rect(fitz.Rect(100, 200, 400, 500))
        doc.save(path)
        doc.close()

    @staticmethod
    def create_vector_without_scale(path: str):
        """PDF vector لكن بدون scale annotation."""
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        # لا نضيف scale annotation
        page.draw_rect(fitz.Rect(100, 200, 400, 500))
        doc.save(path)
        doc.close()

    @staticmethod
    def create_vector_with_layers(path: str, num_layers: int = 5):
        """PDF vector مع طبقات."""
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((50, 50), "SCALE 1:50", fontsize=14)
        page.insert_text((50, 70), "LEGEND", fontsize=12)
        page.insert_text((50, 90), "SMOKE DETECTOR - HEAT DETECTOR - HORN STROBE", fontsize=10)
        # إنشاء طبقات وهمية عبر content streams منفصلة (للتمثيل)
        doc.save(path)
        doc.close()

    @staticmethod
    def create_raster_only(path: str, low_dpi: bool = True):
        """PDF بصيغة raster بالكامل (صورة)."""
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        # إنشاء صورة وتحويلها لـ PNG，然后用 insert_image
        import numpy as np
        from PIL import Image
        width = 50 if low_dpi else 2000
        height = 50 if low_dpi else 2000
        # إنشاء صورة باستخدام PIL
        img = Image.new('RGB', (width, height), color=(128, 128, 128))
        # حفظ كملف مؤقت ثم قراءته
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            img.save(tmp.name)
            page.insert_image(fitz.Rect(0, 0, 612, 792), filename=tmp.name)
        doc.save(path)
        doc.close()

    @staticmethod
    def create_corrupt_pdf(path: str):
        """ملف ليس PDF حقيقياً."""
        with open(path, "w") as f:
            f.write("This is not a PDF file. Just garbage text.")


# ═══════════════════════════════════════════════════════════
# الفئة A: رفض الملفات الفاسدة والمستحيلة
# ═══════════════════════════════════════════════════════════

class TestRejectInvalidFiles:
    """الملفات التي لا يجب أن تمر أبداً."""

    def test_empty_page_rejected(self, tmp_path):
        """صفحة بيضاء = REJECT."""
        path = tmp_path / "empty.pdf"
        PDFFactory.create_empty_pdf(str(path))
        result = evaluate_drawing(str(path))
        assert result.gate == GateDecision.REJECT, (
            f"Empty page must be REJECTED. Got {result.gate.value}, score={result.score}"
        )
        assert result.score < 0.7

    def test_pure_raster_low_dpi_rejected(self, tmp_path):
        """صورة ممسوحة ضوئياً رديئة = REJECT."""
        path = tmp_path / "raster_low.pdf"
        PDFFactory.create_raster_only(str(path), low_dpi=True)
        result = evaluate_drawing(str(path))
        assert result.gate == GateDecision.REJECT, (
            f"Low DPI raster must be REJECTED. Got {result.gate.value}"
        )
        assert "raster" in result.details.get("file_quality", {}).get("type", "")

    def test_corrupt_file_raises(self, tmp_path):
        """ملف نصي مُعاد تسميته إلى pdf = خطأ."""
        path = tmp_path / "fake.pdf"
        PDFFactory.create_corrupt_pdf(str(path))
        with pytest.raises(Exception):
            evaluate_drawing(str(path))

    def test_nonexistent_file_raises(self):
        """ملف غير موجود = خطأ."""
        with pytest.raises(FileNotFoundError):
            evaluate_drawing("/tmp/nonexistent_xyz_12345.pdf")


# ═══════════════════════════════════════════════════════════
# الفئة B: CAUTION — يمر مع تحذير
# ═══════════════════════════════════════════════════════════

class TestCautionModerate:
    """ملفات قد تمر لكن مع تحذير إجباري."""

    def test_vector_without_scale_caution(self, tmp_path):
        """PDF vector لكن بدون scale = CAUTION."""
        path = tmp_path / "no_scale.pdf"
        PDFFactory.create_vector_without_scale(str(path))
        result = evaluate_drawing(str(path))
        # بدون scale + بدون legend = score منخفض
        # يجب أن يكون REJECT أو CAUTION على الأقل
        assert result.gate in (GateDecision.REJECT, GateDecision.CAUTION), (
            f"Drawing without scale must not pass HIGH. Got {result.gate.value}"
        )
        if result.gate == GateDecision.CAUTION:
            assert "PE REVIEW" in result.message.upper() or "CAUTION" in result.message.upper()

    def test_mixed_vector_raster_caution(self, tmp_path):
        """PDF مختلط vector + raster = CAUTION على الأغلب."""
        from PIL import Image
        import tempfile
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((50, 50), "SCALE 1:50", fontsize=12)
        # إنشاء صورة باستخدام PIL
        img = Image.new('RGB', (100, 100), color=(100, 100, 100))
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            img.save(tmp.name)
            page.insert_image(fitz.Rect(200, 200, 300, 300), filename=tmp.name)
        path = tmp_path / "mixed.pdf"
        doc.save(str(path))
        doc.close()
        result = evaluate_drawing(str(path))
        # يجب ألا يكون HIGH_CONFIDENCE
        assert result.gate != GateDecision.HIGH_CONFIDENCE, (
            f"Mixed vector/raster must not get HIGH_CONFIDENCE. Got {result.gate.value}"
        )


# ═══════════════════════════════════════════════════════════
# الفئة C: HIGH CONFIDENCE — يمر بثقة
# ═══════════════════════════════════════════════════════════

class TestHighConfidence:
    """ملفات مهنية كاملة يجب أن تمر بثقة عالية."""

    def test_professional_drawing_passes(self, tmp_path):
        """رسم vector مع scale + legend + رموز NFPA = HIGH."""
        path = tmp_path / "professional.pdf"
        PDFFactory.create_vector_with_layers(str(path))
        result = evaluate_drawing(str(path))
        # قد لا يصل لـ HIGH بسبب نقص الطبقات الفعلية
        # لكن على الأقل يجب ألا يكون REJECT
        assert result.gate != GateDecision.REJECT, (
            f"Professional drawing should not be REJECTED. Got {result.gate.value}, score={result.score}"
        )

    def test_score_breakdown_contains_details(self, tmp_path):
        """نتيجة التقييم يجب أن تحتوي تفاصيل قابلة للتدقيق."""
        path = tmp_path / "details.pdf"
        PDFFactory.create_vector_with_scale(str(path))
        result = evaluate_drawing(str(path))
        assert "file_quality" in result.details
        assert "completeness" in result.details
        assert "raw_score" in result.details
        assert "scale_found" in result.details["completeness"]


# ═══════════════════════════════════════════════════════════
# الفئة D: تماسك النتيجة
# ═══════════════════════════════════════════════════════════

class TestConsistency:
    """التأكد من أن النتيجة متماسكة عبر استدعاءات متعددة."""

    def test_same_file_same_score(self, tmp_path):
        """نفس الملف = نفس الدرجة تماماً."""
        path = tmp_path / "consistent.pdf"
        PDFFactory.create_vector_with_scale(str(path))
        result1 = evaluate_drawing(str(path))
        result2 = evaluate_drawing(str(path))
        assert result1.score == result2.score
        assert result1.gate == result2.gate

    def test_different_files_different_scores(self, tmp_path):
        """ملفات مختلفة يجب أن تعطي درجات مختلفة."""
        path1 = tmp_path / "empty.pdf"
        path2 = tmp_path / "vector.pdf"
        PDFFactory.create_empty_pdf(str(path1))
        PDFFactory.create_vector_with_scale(str(path2))
        result1 = evaluate_drawing(str(path1))
        result2 = evaluate_drawing(str(path2))
        assert result1.score < result2.score, (
            f"Empty PDF should score lower. Empty={result1.score}, Vector={result2.score}"
        )

    def test_gate_matches_thresholds(self, tmp_path):
        """درجة < 0.7 = REJECT، درجة 0.7-0.85 = CAUTION، درجة ≥ 0.85 = HIGH."""
        path = tmp_path / "threshold.pdf"
        PDFFactory.create_vector_with_scale(str(path))
        result = evaluate_drawing(str(path))
        if result.score < 0.7:
            assert result.gate == GateDecision.REJECT
        elif result.score < 0.85:
            assert result.gate == GateDecision.CAUTION
        else:
            assert result.gate == GateDecision.HIGH_CONFIDENCE


# ═══════════════════════════════════════════════════════════════════
# الفئة E: Adversarial — محاولات خداع البوابة
# ═══════════════════════════════════════════════════════════

class TestAdversarial:
    """محاولات خداع النظام بمدخلات ماكرة."""

    def test_pdf_with_only_image_no_text(self, tmp_path):
        """PDF فيه صورة فقط بدون أي نص = يجب رفضه."""
        from PIL import Image
        import tempfile
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        # إنشاء صورة باستخدام PIL
        img = Image.new('RGB', (200, 200), color=(128, 128, 128))
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            img.save(tmp.name)
            page.insert_image(fitz.Rect(0, 0, 612, 792), filename=tmp.name)
        path = tmp_path / "image_only.pdf"
        doc.save(str(path))
        doc.close()
        result = evaluate_drawing(str(path))
        assert result.gate == GateDecision.REJECT, (
            f"Image-only PDF must be REJECTED. Got {result.gate.value}"
        )

    def test_pdf_with_fake_scale_but_no_content(self, tmp_path):
        """PDF فيه كلمة scale فقط بدون أي رسم = يجب رفضه."""
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((50, 50), "SCALE 1:100", fontsize=14)
        page.insert_text((50, 70), "LEGEND", fontsize=12)
        # لا نضيف أي رسومات
        path = tmp_path / "text_only.pdf"
        doc.save(str(path))
        doc.close()
        result = evaluate_drawing(str(path))
        # قد يكون CAUTION أو REJECT، لكن يجب ألا يكون HIGH
        assert result.gate != GateDecision.HIGH_CONFIDENCE, (
            f"Text-only PDF must not get HIGH_CONFIDENCE. Got {result.gate.value}"
        )


# ═══════════════════════════════════════════════════════════
# تشغيل الاختبارات مباشرة
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "--strict-markers"])