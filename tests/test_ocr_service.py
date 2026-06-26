"""tests/test_ocr_service.py — OCR + ScanToBIM Tests"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.services.ocr_service import OCRService, OCRResult
from backend.services.scan_to_bim import ScanToBIMService, ScanToBIMResult


@pytest.fixture
def test_image():
    """Create a test image with room/area text."""
    from PIL import Image, ImageDraw
    img = Image.new('RGB', (800, 400), color='white')
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "Room 101 Area 25.5 sqm", fill='black')
    draw.text((50, 150), "Corridor Area 12.0 m2", fill='black')
    path = os.path.join(tempfile.gettempdir(), "test_plan.png")
    img.save(path)
    yield path
    if os.path.exists(path):
        os.unlink(path)


class TestOCRServiceInit:
    def test_creates_instance(self):
        svc = OCRService()
        assert svc is not None

    def test_status(self):
        svc = OCRService()
        status = svc.get_status()
        assert "tesseract_available" in status
        assert "pytesseract_available" in status
        assert isinstance(status["supported_extensions"], list)


class TestOCRProcessImage:
    def test_process_image(self, test_image):
        svc = OCRService()
        result = svc.process(test_image, correlation_id="test-ocr")
        assert isinstance(result, OCRResult)
        assert result.page_count == 1
        assert result.correlation_id == "test-ocr"
        assert result.text  # Should have some text

    def test_process_with_auto_correlation_id(self, test_image):
        svc = OCRService()
        result = svc.process(test_image)
        assert result.correlation_id.startswith("ocr-")

    def test_process_nonexistent_file_raises(self):
        svc = OCRService()
        with pytest.raises(ValueError):
            svc.process("/tmp/nonexistent_xyz.png")

    def test_process_wrong_extension_rejected(self):
        svc = OCRService()
        with pytest.raises(ValueError):
            svc.process("/tmp/test.exe")


class TestOCRSecurity:
    def test_path_traversal_rejected(self):
        svc = OCRService()
        with pytest.raises(ValueError):
            svc.process("../../etc/passwd")

    def test_null_byte_rejected(self):
        svc = OCRService()
        with pytest.raises(ValueError):
            svc.process("/tmp/test.png\x00.exe")


class TestScanToBIM:
    def test_process_image(self, test_image):
        svc = ScanToBIMService()
        result = svc.process(test_image, correlation_id="test-s2b")
        assert isinstance(result, ScanToBIMResult)
        assert result.correlation_id == "test-s2b"
        assert result.requires_human_review is True  # Always True

    def test_always_requires_human_review(self, test_image):
        svc = ScanToBIMService()
        result = svc.process(test_image)
        assert result.requires_human_review is True

    def test_warnings_on_low_confidence(self, test_image):
        svc = ScanToBIMService()
        result = svc.process(test_image)
        # May have warnings depending on OCR quality
        assert isinstance(result.warnings, list)

    def test_correlation_id_auto(self, test_image):
        svc = ScanToBIMService()
        result = svc.process(test_image)
        assert result.correlation_id.startswith("s2b-")

    def test_nonexistent_file_raises(self):
        svc = ScanToBIMService()
        with pytest.raises(ValueError):
            svc.process("/tmp/nonexistent_xyz.png")


class TestScanToBIMPatterns:
    def test_area_pattern_sqm(self):
        import re
        from backend.services.scan_to_bim import ScanToBIMService
        svc = ScanToBIMService()
        pattern = svc.AREA_PATTERNS[0]
        match = pattern.search("25.5 sqm")
        assert match is not None
        assert float(match.group(1)) == 25.5

    def test_area_pattern_m2(self):
        import re
        from backend.services.scan_to_bim import ScanToBIMService
        svc = ScanToBIMService()
        pattern = svc.AREA_PATTERNS[0]
        match = pattern.search("12.0 m2")
        assert match is not None
        assert float(match.group(1)) == 12.0

    def test_room_name_pattern(self):
        import re
        from backend.services.scan_to_bim import ScanToBIMService
        svc = ScanToBIMService()
        pattern = svc.ROOM_PATTERNS[0]
        match = pattern.search("Room 101")
        assert match is not None

    def test_room_type_pattern(self):
        import re
        from backend.services.scan_to_bim import ScanToBIMService
        svc = ScanToBIMService()
        pattern = svc.ROOM_PATTERNS[1]
        match = pattern.search("Office Area")
        assert match is not None
