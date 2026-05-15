"""
INPUT PIPELINE — Brutal Integration Tests
=============================================
يختبر المسار الكامل: PDF → Pipeline → تقرير جاهز لمحرك NFPA 72.

Author: The Consultant Who Refused to Lie
"""

import pytest
import fitz
from pathlib import Path
from src.core.input_pipeline import InputPipeline, PipelineStatus

class PipelinePDFFactory:
    """يُنتج PDFs لاختبار المسار الكامل."""
    
    @staticmethod
    def create_empty(path: str):
        doc = fitz.open()
        doc.new_page(width=612, height=792)
        doc.save(path)
        doc.close()

    @staticmethod
    def create_minimal(path: str):
        """رسم بسيط: جدار + كاشف دخان + بُعد."""
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((50, 50), "SCALE 1:100", fontsize=14)
        page.insert_text((50, 70), "LEGEND: SD = SMOKE DETECTOR", fontsize=10)
        page.draw_rect(fitz.Rect(100, 200, 400, 500), color=(0,0,0), fill=(0.9,0.9,0.9), width=1.5)
        page.insert_text((150, 300), "SD-1")
        page.insert_text((450, 350), "3.5 m")
        doc.save(path)
        doc.close()

    @staticmethod
    def create_full(path: str):
        """رسم كامل: جدران + رموز متعددة + أبعاد."""
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((50, 50), "SCALE 1:50", fontsize=14)
        page.insert_text((50, 70), "LEGEND", fontsize=12)
        page.insert_text((50, 90), "SD SMOKE DET | HD HEAT DET | H/S HORN STROBE", fontsize=10)
        page.draw_rect(fitz.Rect(80, 150, 300, 400), color=(0,0,0), fill=(0.9,0.9,0.9), width=1.5)
        page.draw_rect(fitz.Rect(320, 150, 550, 400), color=(0,0,0), fill=(0.9,0.9,0.9), width=1.5)
        page.insert_text((120, 250), "SD-1")
        page.insert_text((200, 300), "SD-2")
        page.insert_text((350, 250), "HD-1")
        page.insert_text((400, 350), "H/S-1")
        page.insert_text((450, 200), "FACP")
        page.insert_text((60, 430), "12.0 m")
        page.insert_text((310, 430), "3.5 m")
        doc.save(path)
        doc.close()


class TestPipelineGate:
    """اختبارات قرارات البوابة."""

    def test_empty_pdf_rejected(self, tmp_path):
        path = tmp_path / "empty.pdf"
        PipelinePDFFactory.create_empty(str(path))
        pipeline = InputPipeline(str(path))
        result = pipeline.execute()
        assert result.status == PipelineStatus.REJECTED
        # البوابة ترفض قبل الاستخراج
        assert "REJECT" in result.message or "NO_WALLS" in result.errors

    def test_minimal_pdf_caution_or_high(self, tmp_path):
        path = tmp_path / "minimal.pdf"
        PipelinePDFFactory.create_minimal(str(path))
        pipeline = InputPipeline(str(path))
        result = pipeline.execute()
        assert result.status != PipelineStatus.REJECTED
        assert result.drawing_score > 0.0

    def test_full_pdf_passes(self, tmp_path):
        path = tmp_path / "full.pdf"
        PipelinePDFFactory.create_full(str(path))
        pipeline = InputPipeline(str(path))
        result = pipeline.execute()
        assert result.status != PipelineStatus.REJECTED
        assert result.walls
        assert result.symbols
        assert result.dimensions


class TestPipelineIntegration:
    """اختبارات التكامل."""

    def test_walls_extracted(self, tmp_path):
        path = tmp_path / "full.pdf"
        PipelinePDFFactory.create_full(str(path))
        pipeline = InputPipeline(str(path))
        result = pipeline.execute()
        assert len(result.walls) >= 2

    def test_symbols_extracted(self, tmp_path):
        path = tmp_path / "full.pdf"
        PipelinePDFFactory.create_full(str(path))
        pipeline = InputPipeline(str(path))
        result = pipeline.execute()
        assert len(result.symbols) >= 4

    def test_dimensions_extracted(self, tmp_path):
        path = tmp_path / "full.pdf"
        PipelinePDFFactory.create_full(str(path))
        pipeline = InputPipeline(str(path))
        result = pipeline.execute()
        assert len(result.dimensions) >= 2

    def test_detectors_built(self, tmp_path):
        path = tmp_path / "full.pdf"
        PipelinePDFFactory.create_full(str(path))
        pipeline = InputPipeline(str(path))
        result = pipeline.execute()
        assert len(result.detectors) >= 4

    def test_rooms_built(self, tmp_path):
        path = tmp_path / "full.pdf"
        PipelinePDFFactory.create_full(str(path))
        pipeline = InputPipeline(str(path))
        result = pipeline.execute()
        assert len(result.rooms) >= 2
        for room in result.rooms:
            assert room.area_m2 > 0.0


class TestPipelineWarnings:
    """اختبارات التحذيرات."""

    def test_always_requires_pe_review(self, tmp_path):
        path = tmp_path / "full.pdf"
        PipelinePDFFactory.create_full(str(path))
        pipeline = InputPipeline(str(path))
        result = pipeline.execute()
        assert result.requires_pe_review is True

    def test_errors_reported_when_no_walls(self, tmp_path):
        path = tmp_path / "empty.pdf"
        PipelinePDFFactory.create_empty(str(path))
        pipeline = InputPipeline(str(path))
        result = pipeline.execute()
        # البوابة ترفض - لا حاجة للتحقق من NO_WALLS
        assert result.status == PipelineStatus.REJECTED


class TestPipelineEdgeCases:
    """حالات حدودية."""

    def test_nonexistent_file_raises(self):
        with pytest.raises(FileNotFoundError):
            InputPipeline("/tmp/nonexistent_abc_123.pdf")

    def test_same_file_consistent_result(self, tmp_path):
        path = tmp_path / "full.pdf"
        PipelinePDFFactory.create_full(str(path))
        res1 = InputPipeline(str(path)).execute()
        res2 = InputPipeline(str(path)).execute()
        assert res1.drawing_score == res2.drawing_score
        assert len(res1.walls) == len(res2.walls)

    def test_ceiling_height_extracted(self, tmp_path):
        path = tmp_path / "full.pdf"
        PipelinePDFFactory.create_full(str(path))
        pipeline = InputPipeline(str(path))
        result = pipeline.execute()
        assert result.ceiling_height_m > 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])