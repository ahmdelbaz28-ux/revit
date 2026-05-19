"""
COVERAGE PIPELINE — Brutal End-to-End Tests
==========================================
يختبر المسار الكامل: PDF → CoverageReport

Author: The Consultant Who Refused to Lie
"""

import pytest
import fitz
from pathlib import Path
from src.core.coverage_pipeline import (
    CoveragePipeline,
    run_coverage_analysis,
    CoverageStatus,
    RoomCoverageReport,
    CoverageReport
)
from src.core.input_pipeline import InputPipeline, PipelineResult


class PDFactory:
    """يُنتج PDFs للاختبار."""
    
    @staticmethod
    def create_empty(path: str):
        doc = fitz.open()
        doc.new_page(width=612, height=792)
        doc.save(path)
        doc.close()

    @staticmethod
    def create_simple(path: str):
        """غرفة + كاشف."""
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((50, 50), "SCALE 1:100", fontsize=14)
        page.draw_rect(fitz.Rect(100, 150, 400, 350), color=(0,0,0), fill=(0.9,0.9,0.9), width=1.5)
        page.insert_text((250, 250), "SD-1")
        page.insert_text((50, 400), "10 m")
        doc.save(path)
        doc.close()

    @staticmethod
    def create_multi_detectors(path: str):
        """غرفة + mehrere كواشف."""
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((50, 50), "SCALE 1:50", fontsize=14)
        page.draw_rect(fitz.Rect(100, 150, 400, 350), color=(0,0,0), fill=(0.9,0.9,0.9), width=1.5)
        page.insert_text((150, 200), "SD-1 SD-2")
        page.insert_text((350, 300), "HD-1")
        doc.save(path)
        doc.close()

    @staticmethod
    def create_no_detectors(path: str):
        """غرفة بدون كواشف."""
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((50, 50), "SCALE 1:100", fontsize=14)
        page.draw_rect(fitz.Rect(100, 150, 400, 350), color=(0,0,0), fill=(0.9,0.9,0.9), width=1.5)
        page.insert_text((50, 400), "10 m")
        doc.save(path)
        doc.close()

    @staticmethod
    def create_high_ceiling(path: str):
        """سقف عالٍ."""
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((50, 50), "SCALE 1:50", fontsize=14)
        page.draw_rect(fitz.Rect(100, 150, 400, 350), color=(0,0,0), fill=(0.9,0.9,0.9), width=1.5)
        page.insert_text((150, 200), "SD-1 SD-2")
        page.insert_text((50, 400), "10 m")
        # ارتفاع غير قياسي
        doc.save(path)
        doc.close()


class TestGateRejected:
    """اختبارات الرفض من البوابة."""

    def test_empty_pdf_returns_fail(self, tmp_path):
        path = tmp_path / "empty.pdf"
        PDFactory.create_empty(str(path))
        report = run_coverage_analysis(str(path))
        
        assert report.status == CoverageStatus.FAIL
        assert "rejected" in report.message.lower() or "NO" in report.errors

    def test_no_detectors_returns_fail(self, tmp_path):
        path = tmp_path / "no_detectors.pdf"
        PDFactory.create_no_detectors(str(path))
        report = run_coverage_analysis(str(path))
        
        assert report.status == CoverageStatus.FAIL
        assert any("NO_DETECTORS" in e for e in report.errors)


class TestCoverageCalculation:
    """اختبارات حساب التغطية."""

    def test_single_detector_coverage(self, tmp_path):
        path = tmp_path / "simple.pdf"
        PDFactory.create_simple(str(path))
        report = run_coverage_analysis(str(path))
        
        assert report.total_detectors >= 1
        assert report.total_rooms >= 1

    def test_multi_detectors_extracted(self, tmp_path):
        path = tmp_path / "multi.pdf"
        PDFactory.create_multi_detectors(str(path))
        report = run_coverage_analysis(str(path))
        
        assert report.total_detectors >= 3

    def test_room_area_extracted(self, tmp_path):
        path = tmp_path / "simple.pdf"
        PDFactory.create_simple(str(path))
        report = run_coverage_analysis(str(path))
        
        assert report.total_rooms >= 1
        assert report.room_reports[0].room_area_m2 > 0


class TestStatusesAndWarnings:
    """اختبارات الحالات والتحذيرات."""

    def test_always_requires_pe_review(self, tmp_path):
        path = tmp_path / "simple.pdf"
        PDFactory.create_simple(str(path))
        report = run_coverage_analysis(str(path))
        
        # يجب أن يتطلب مراجعة دائماً
        assert report.requires_pe_review is True

    def test_status_is_valid_enum(self, tmp_path):
        path = tmp_path / "simple.pdf"
        PDFactory.create_simple(str(path))
        report = run_coverage_analysis(str(path))
        
        # Status must be a valid CoverageStatus
        assert report.status in [
            CoverageStatus.PASS,
            CoverageStatus.FAIL,
            CoverageStatus.CAUTION,
            CoverageStatus.REQUIRES_PE_REVIEW
        ]

    def test_room_report_has_all_fields(self, tmp_path):
        path = tmp_path / "simple.pdf"
        PDFactory.create_simple(str(path))
        report = run_coverage_analysis(str(path))
        
        rr = report.room_reports[0]
        assert hasattr(rr, 'room_index')
        assert hasattr(rr, 'room_area_m2')
        assert hasattr(rr, 'detectors_count')
        assert hasattr(rr, 'coverage_pct')
        assert hasattr(rr, 'spacing_ok')
        assert hasattr(rr, 'warnings')
        assert hasattr(rr, 'status')


class TestEdgeCases:
    """حالات حدودية."""

    def test_nonexistent_file_raises(self):
        with pytest.raises(Exception):
            run_coverage_analysis("/tmp/nonexistent_xyz.pdf")

    def test_drawing_score_in_report(self, tmp_path):
        path = tmp_path / "simple.pdf"
        PDFactory.create_simple(str(path))
        report = run_coverage_analysis(str(path))
        
        assert report.drawing_score >= 0.0
        assert report.drawing_score <= 1.0

    def test_ceiling_height_in_report(self, tmp_path):
        path = tmp_path / "simple.pdf"
        PDFactory.create_simple(str(path))
        report = run_coverage_analysis(str(path))
        
        assert report.ceiling_height_m > 0


class TestFullPipeline:
    """اختبارات المسار الكامل."""

    def test_pipeline_produces_valid_report(self, tmp_path):
        path = tmp_path / "simple.pdf"
        PDFactory.create_simple(str(path))
        
        # Full pipeline: InputPipeline -> CoveragePipeline
        pipeline = InputPipeline(str(path))
        result = pipeline.execute()
        
        coverage = CoveragePipeline(result)
        final_report = coverage.execute()
        
        assert isinstance(final_report, CoverageReport)
        assert final_report.total_rooms >= 0
        assert final_report.total_detectors >= 0
        assert final_report.status in [
            CoverageStatus.PASS,
            CoverageStatus.FAIL,
            CoverageStatus.CAUTION,
            CoverageStatus.REQUIRES_PE_REVIEW
        ]

    def test_consistent_results(self, tmp_path):
        path = tmp_path / "simple.pdf"
        PDFactory.create_simple(str(path))
        
        report1 = run_coverage_analysis(str(path))
        report2 = run_coverage_analysis(str(path))
        
        assert report1.status == report2.status
        assert report1.total_rooms == report2.total_rooms


if __name__ == "__main__":
    pytest.main([__file__, "-v"])