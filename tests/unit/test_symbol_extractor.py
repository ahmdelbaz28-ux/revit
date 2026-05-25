"""
SYMBOL EXTRACTOR — Brutal Validation Tests
=============================================
يختبر أن المستخلص:
- يجد الرموز الحقيقية.
- لا يخترع رموزاً وهمية.
- يوسم كل رمز بـ MODERATE (لا ثقة عمياء).

Author: The Consultant Who Refused to Lie
"""

import pytest
import fitz
from pathlib import Path
from src.core.symbol_extractor import (
    SymbolExtractor,
    SymbolElement,
    SymbolType,
    extract_symbols_from_pdf
)

class SymbolPDFFactory:
    @staticmethod
    def create_blank(path: str):
        doc = fitz.open()
        doc.new_page(width=612, height=792)
        doc.save(path)
        doc.close()

    @staticmethod
    def create_with_smoke_detectors(path: str):
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((100, 100), "SD-1")
        page.insert_text((200, 200), "SMOKE")
        doc.save(path)
        doc.close()

    @staticmethod
    def create_mixed_symbols(path: str):
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((100, 100), "SD-101")
        page.insert_text((100, 150), "HEAT DETECTOR")
        page.insert_text((100, 200), "PULL STATION")
        page.insert_text((100, 250), "HORN/STROBE")
        page.insert_text((100, 300), "FACP")
        doc.save(path)
        doc.close()

    @staticmethod
    def create_noise_only(path: str):
        """كلمات لا علاقة لها بالحماية."""
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((100, 100), "OFFICE")
        page.insert_text((100, 150), "CONFERENCE")
        page.insert_text((100, 200), "WINDOW")
        doc.save(path)
        doc.close()


class TestSymbolExtraction:
    def test_empty_pdf_returns_no_symbols(self, tmp_path):
        path = tmp_path / "empty.pdf"
        SymbolPDFFactory.create_blank(str(path))
        symbols = extract_symbols_from_pdf(str(path))
        assert len(symbols) == 0

    def test_smoke_detectors_found(self, tmp_path):
        path = tmp_path / "smoke.pdf"
        SymbolPDFFactory.create_with_smoke_detectors(str(path))
        symbols = extract_symbols_from_pdf(str(path))
        assert len(symbols) >= 1
        assert any(s.symbol_type == SymbolType.SMOKE_DETECTOR for s in symbols)

    def test_all_symbols_tagged_moderate(self, tmp_path):
        path = tmp_path / "mixed.pdf"
        SymbolPDFFactory.create_mixed_symbols(str(path))
        symbols = extract_symbols_from_pdf(str(path))
        for s in symbols:
            assert s.confidence.value == "MODERATE", (
                f"Every extracted symbol must be MODERATE. Got {s.confidence} for {s.symbol_type}"
            )

    def test_mixed_symbols_found_correct_types(self, tmp_path):
        path = tmp_path / "mixed.pdf"
        SymbolPDFFactory.create_mixed_symbols(str(path))
        symbols = extract_symbols_from_pdf(str(path))
        types = {s.symbol_type for s in symbols}
        assert SymbolType.SMOKE_DETECTOR in types
        assert SymbolType.HEAT_DETECTOR in types
        assert SymbolType.PULL_STATION in types
        assert SymbolType.HORN_STROBE in types
        assert SymbolType.FIRE_ALARM_PANEL in types

    def test_noise_returns_no_symbols(self, tmp_path):
        path = tmp_path / "noise.pdf"
        SymbolPDFFactory.create_noise_only(str(path))
        symbols = extract_symbols_from_pdf(str(path))
        assert len(symbols) == 0, "Should not create symbols from random words"

    def test_symbol_bbox_is_valid(self, tmp_path):
        path = tmp_path / "smoke.pdf"
        SymbolPDFFactory.create_with_smoke_detectors(str(path))
        symbols = extract_symbols_from_pdf(str(path))
        for s in symbols:
            assert len(s.bbox) == 4
            assert s.bbox[0] <= s.bbox[2] and s.bbox[1] <= s.bbox[3]

    def test_nonexistent_file_raises(self):
        with pytest.raises(FileNotFoundError):
            extract_symbols_from_pdf("/tmp/nonexistent_xyz.pdf")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])