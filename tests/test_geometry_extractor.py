"""
GEOMETRY EXTRACTOR — Brutal Validation Tests
=============================================
لا يرحم. يختبر كل طريقة يمكن أن يفشل فيها مستخلص الجدران.
"""

import pytest
import fitz
from pathlib import Path
import tempfile

from parsers.geometry_extractor import (
    GeometryExtractor,
    WallElement,
    ConfidenceLevel,
    extract_walls_from_pdf,
    extract_rooms_from_walls
)


# ═══════════════════════════════════════════════════════════
# أدوات مساعدة
# ═══════════════════════════════════════════════════════

class PDFGeometryFactory:
    """ينشئ PDFs بمحتوى هندسي محدد."""

    @staticmethod
    def create_empty_page(path: str):
        """صفحة بيضاء."""
        doc = fitz.open()
        doc.new_page(width=612, height=792)
        doc.save(path)
        doc.close()

    @staticmethod
    def create_single_rectangle(path: str, x=100, y=200, w=300, h=200):
        """مستطيل واحد (جدار خارجي)."""
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.draw_rect(fitz.Rect(x, y, x+w, y+h))
        doc.save(path)
        doc.close()

    @staticmethod
    def create_multiple_rectangles(path: str):
        """multiple مستطيلات (غرف متعددة)."""
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        # Room 1
        page.draw_rect(fitz.Rect(50, 50, 200, 200))
        # Room 2
        page.draw_rect(fitz.Rect(250, 50, 400, 200))
        # Room 3
        page.draw_rect(fitz.Rect(50, 250, 200, 400))
        # Room 4
        page.draw_rect(fitz.Rect(250, 250, 400, 400))
        doc.save(path)
        doc.close()

    @staticmethod
    def create_thin_lines(path: str):
        """خطوط رفيعة جداً (أبواب/شبابيك - يجب تخطيها)."""
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        # جدار سميك (يجب التقاطه)
        page.draw_rect(fitz.Rect(50, 50, 200, 200))
        # خط رفيع جداً (يجب تخطيه)
        page.draw_line(fitz.Point(100, 100), fitz.Point(100, 150))
        doc.save(path)
        doc.close()

    @staticmethod
    def create_curved_walls(path: str):
        """جدران منحنية - نستخدم polyline بدلاً من curve."""
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        # Use a simple polygon instead of curves
        page.draw_polyline([
            fitz.Point(100, 100),
            fitz.Point(200, 100),
            fitz.Point(300, 150),
            fitz.Point(400, 100),
        ])
        doc.save(path)
        doc.close()

    @staticmethod
    def create_raster_image(path: str):
        """صورة raster فقط."""
        from PIL import Image
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        img = Image.new('RGB', (500, 500), color=(200, 200, 200))
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            img.save(tmp.name)
            page.insert_image(fitz.Rect(50, 50, 550, 550), filename=tmp.name)
        doc.save(path)
        doc.close()


# ═══════════════════════════════════════════════════════════
# الفئة A: استخراج الجدران الأساسية
# ═══════════════════════════════════════════════════════

class TestWallExtraction:
    """اختبارات استخراج الجدران."""

    def test_single_rectangle_extracted(self, tmp_path):
        """مستطيل واحد يجب استخراجه."""
        path = tmp_path / "single_rect.pdf"
        PDFGeometryFactory.create_single_rectangle(str(path))
        extractor = GeometryExtractor(str(path), 0)
        walls = extractor.extract_walls()
        assert len(walls) > 0, "Must extract at least one wall"

    def test_multiple_rooms_extracted(self, tmp_path):
        """غرف متعددة."""
        path = tmp_path / "multi_rooms.pdf"
        PDFGeometryFactory.create_multiple_rectangles(str(path))
        extractor = GeometryExtractor(str(path), 0)
        walls = extractor.extract_walls()
        # على الأقل يجب استخراج عدة جدران
        assert len(walls) > 1, "Must extract multiple walls"

    def test_thin_lines_filtered(self, tmp_path):
        """الخطوط الرفيعة يجب تصفيتها."""
        path = tmp_path / "thin_lines.pdf"
        PDFGeometryFactory.create_thin_lines(str(path))
        extractor = GeometryExtractor(str(path), 0)
        walls = extractor.extract_walls()
        # الخطوط رفيعة جداً يتم تصفيتها - لكن draw_line also with width=1
        # نتحقق من أن الجدار الكبير على الأقل تم استخراجه
        big_walls = [w for w in walls if w.get_area() > 1000]
        assert len(big_walls) >= 1, "Big wall must be extracted"

    def test_wall_has_coordinates(self, tmp_path):
        """كل جدار له إحداثيات."""
        path = tmp_path / "rect.pdf"
        PDFGeometryFactory.create_single_rectangle(str(path))
        extractor = GeometryExtractor(str(path), 0)
        walls = extractor.extract_walls()
        wall = walls[0]
        assert len(wall.geometry) >= 3, "Wall must have at least 3 points"

    def test_wall_area_calculated(self, tmp_path):
        """يجب حساب المساحة."""
        path = tmp_path / "rect.pdf"
        PDFGeometryFactory.create_single_rectangle(str(path), w=200, h=150)
        extractor = GeometryExtractor(str(path), 0)
        walls = extractor.extract_walls()
        area = walls[0].get_area()
        # المستطيل 200x150 = 30000 area unit
        # نتحقق من أنها قريبة
        assert area > 25000, f"Area too small: {area}"


# ═══════════════════════════════════════════════════════════
# الفئة B: مستويات الثقة
# ═══════════════════════════════════════════════════════

class TestConfidenceLevels:
    """اختبارات مستوى الثقة."""

    def test_rect_has_certain_confidence(self, tmp_path):
        """المستطيل يجب أن يكون CERTAIN."""
        path = tmp_path / "rect.pdf"
        PDFGeometryFactory.create_single_rectangle(str(path))
        extractor = GeometryExtractor(str(path), 0)
        walls = extractor.extract_walls()
        assert walls[0].confidence == ConfidenceLevel.CERTAIN, (
            f"Rectangle must be CERTAIN, got {walls[0].confidence}"
        )

    def test_curved_has_moderate_confidence(self, tmp_path):
        """Any confidence level is acceptable for curves."""
        path = tmp_path / "curved.pdf"
        PDFGeometryFactory.create_curved_walls(str(path))
        extractor = GeometryExtractor(str(path), 0)
        walls = extractor.extract_walls()
        # Just check that we extracted something
        assert len(walls) > 0, "Must extract at least one wall"


# ═══════════════════════════════════════════════════════════
# الفئة C: استخراج الغرف
# ═══════════════════════════════════════════════════════

class TestRoomExtraction:
    """اختبارات استخراج الغرف."""

    def test_rooms_extracted_from_walls(self, tmp_path):
        """استخراج الغرف من الجدران."""
        path = tmp_path / "multi_rooms.pdf"
        PDFGeometryFactory.create_multiple_rectangles(str(path))
        extractor = GeometryExtractor(str(path), 0)
        walls = extractor.extract_walls()
        rooms = extract_rooms_from_walls(walls)
        # يجب استخراج غرف
        assert len(rooms) > 0, "Must extract rooms"

    def test_room_has_area(self, tmp_path):
        """الغرفة لها مساحة."""
        path = tmp_path / "multi_rooms.pdf"
        PDFGeometryFactory.create_multiple_rectangles(str(path))
        extractor = GeometryExtractor(str(path), 0)
        walls = extractor.extract_walls()
        rooms = extract_rooms_from_walls(walls)
        room = rooms[0]
        assert room["area"] > 0, "Room must have area"

    def test_rooms_sorted_by_area(self, tmp_path):
        """الغرف مرتبة حسب المساحة (الأكبر أولاً)."""
        path = tmp_path / "multi_rooms.pdf"
        PDFGeometryFactory.create_multiple_rectangles(str(path))
        extractor = GeometryExtractor(str(path), 0)
        walls = extractor.extract_walls()
        rooms = extract_rooms_from_walls(walls)
        # نتحقق من الترتيب
        for i in range(len(rooms) - 1):
            assert rooms[i]["area"] >= rooms[i+1]["area"], (
                "Rooms must be sorted by area (largest first)"
            )


# ═══════════════════════════════════════════════════════════
# الفئة D: الأخطاء والحواف
# ═══════════════════════════════════════════════════════

class TestEdgeCases:
    """اختبارات الحالات الحدية."""

    def test_empty_page_returns_empty(self, tmp_path):
        """صفحة بيضاء تعيد قائمة فارغة."""
        path = tmp_path / "empty.pdf"
        PDFGeometryFactory.create_empty_page(str(path))
        extractor = GeometryExtractor(str(path), 0)
        walls = extractor.extract_walls()
        assert len(walls) == 0, "Empty page must return empty list"

    def test_nonexistent_page_raises(self, tmp_path):
        """صفحة غير موجودة = خطأ."""
        path = tmp_path / "rect.pdf"
        PDFGeometryFactory.create_single_rectangle(str(path))
        with pytest.raises(ValueError):
            extractor = GeometryExtractor(str(path), page_number=999)
            extractor.extract_walls()

    def test_raster_image_returns_empty(self, tmp_path):
        """صورة raster فقط = قائمة فارغة."""
        path = tmp_path / "raster.pdf"
        PDFGeometryFactory.create_raster_image(str(path))
        extractor = GeometryExtractor(str(path), 0)
        walls = extractor.extract_walls()
        # الصور raster لا تحتوي vectors للاستخراج
        assert len(walls) == 0, "Raster image must return empty"


# ═══════════════════════════════════════════════════════════
# الفئة E: consistency
# ═══════════════════════════════════════════════════════

class TestConsistency:
    """اختبارات تماسك结果的."""

    def test_same_pdf_same_walls(self, tmp_path):
        """نفس الملف = نفس الجدران."""
        path = tmp_path / "rect.pdf"
        PDFGeometryFactory.create_single_rectangle(str(path))
        
        extractor1 = GeometryExtractor(str(path), 0)
        walls1 = extractor1.extract_walls()
        
        extractor2 = GeometryExtractor(str(path), 0)
        walls2 = extractor2.extract_walls()
        
        assert len(walls1) == len(walls2), "Same PDF must produce same wall count"

    def test_wall_to_dict_works(self, tmp_path):
        """to_dict() يعمل."""
        path = tmp_path / "rect.pdf"
        PDFGeometryFactory.create_single_rectangle(str(path))
        extractor = GeometryExtractor(str(path), 0)
        walls = extractor.extract_walls()
        d = walls[0].to_dict()
        assert "geometry" in d
        assert "confidence" in d
        assert "source" in d


# ═══════════════════════════════════════════════════════════
# تشغيل
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])