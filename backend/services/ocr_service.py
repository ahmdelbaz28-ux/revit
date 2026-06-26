"""
backend/services/ocr_service.py — OCR Service for Scanned Documents
====================================================================

Converts scanned PDF/blueprint images into machine-readable text using
Tesseract OCR. Designed for the Egyptian/Middle Eastern market where
90% of architectural drawings arrive as scanned PDFs.

CAPABILITIES:
  - OCR on PDF (page-by-page via pdf2image)
  - OCR on images (PNG, JPEG, TIFF, BMP)
  - Multi-language support (English + Arabic)
  - Text extraction with position information
  - Integration with geometry_extractor for wall/room detection

SAFETY-CRITICAL:
  - Path traversal protection via _path_security
  - File size validation
  - OCR results are BEST-EFFORT — always verify against original
  - Failed OCR is flagged, never silently ignored

REFERENCE: NFPA 72-2022 §10.6 (audit trail)
"""

from __future__ import annotations

import logging
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("fireai.services.ocr")

# ── Data Classes ──────────────────────────────────────────────────────────────


@dataclass
class OCRResult:
    """Result from OCR processing."""
    text: str
    confidence: float
    page_count: int
    pages: list[dict[str, Any]] = field(default_factory=list)
    source_path: str = ""
    correlation_id: str = ""
    language: str = "eng"
    processed_at: str = ""

    def __post_init__(self):
        if not self.processed_at:
            self.processed_at = datetime.now(timezone.utc).isoformat()


# ── OCR Service ───────────────────────────────────────────────────────────────


class OCRService:
    """
    OCR service for scanned architectural documents.

    Uses Tesseract OCR with pdf2image for PDF support.
    Gracefully degrades if dependencies are unavailable.
    """

    SUPPORTED_EXTENSIONS = frozenset({
        ".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp",
    })

    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB

    def __init__(self, tesseract_lang: str = "eng"):
        self._tesseract_lang = tesseract_lang
        self._tesseract_available = self._check_tesseract()
        self._pytesseract_available = self._check_pytesseract()
        self._pdf2image_available = self._check_pdf2image()

    def _check_tesseract(self) -> bool:
        """Check if tesseract binary is available."""
        import shutil
        return shutil.which("tesseract") is not None

    def _check_pytesseract(self) -> bool:
        """Check if pytesseract Python package is available."""
        try:
            import pytesseract  # noqa: F401
            return True
        except ImportError:
            return False

    def _check_pdf2image(self) -> bool:
        """Check if pdf2image is available."""
        try:
            from pdf2image import convert_from_path  # noqa: F401
            return True
        except ImportError:
            return False

    # ── Security Gate ─────────────────────────────────────────────────────

    def _validate_path(self, file_path: str) -> Path:
        """Validate input file path."""
        from parsers._path_security import (
            UnsafePathError,
            validate_file_size,
            validate_input_path,
        )
        try:
            safe_path = validate_input_path(
                file_path,
                allowed_extensions=self.SUPPORTED_EXTENSIONS,
                parser_name="OCRService",
            )
            validate_file_size(
                safe_path,
                max_size_bytes=self.MAX_FILE_SIZE,
                parser_name="OCRService",
            )
        except FileNotFoundError as e:
            raise ValueError(f"File not found: {e}") from e
        except UnsafePathError as e:
            raise ValueError(f"SECURITY: {e}") from e
        return safe_path

    # ── Process File ──────────────────────────────────────────────────────

    def process(
        self,
        file_path: str,
        correlation_id: str | None = None,
        language: str | None = None,
    ) -> OCRResult:
        """
        Process a file with OCR.

        Args:
            file_path: Path to PDF or image file.
            correlation_id: Audit trail ID.
            language: OCR language (default: eng, use 'ara' for Arabic).

        Returns:
            OCRResult with extracted text and metadata.
        """
        if correlation_id is None:
            correlation_id = f"ocr-{uuid.uuid4().hex[:12]}"

        lang = language or self._tesseract_lang
        safe_path = self._validate_path(file_path)
        ext = safe_path.suffix.lower()

        logger.info(
            "OCR processing | file=%s | lang=%s | correlation_id=%s",
            safe_path, lang, correlation_id,
        )

        if not self._pytesseract_available:
            raise ValueError(
                "pytesseract not installed. Install with: pip install pytesseract"
            )

        if ext == ".pdf":
            return self._process_pdf(safe_path, lang, correlation_id)
        else:
            return self._process_image(safe_path, lang, correlation_id)

    # ── Process PDF ───────────────────────────────────────────────────────

    def _process_pdf(
        self, file_path: Path, lang: str, correlation_id: str
    ) -> OCRResult:
        """Process a PDF file page by page."""
        import pytesseract
        from pdf2image import convert_from_path

        if not self._pdf2image_available:
            raise ValueError(
                "pdf2image not installed. Install with: pip install pdf2image. "
                "Also requires poppler-utils: apt install poppler-utils"
            )

        pages_data = []
        all_text = []

        try:
            images = convert_from_path(str(file_path), dpi=300)
        except Exception as e:
            raise ValueError(f"PDF to image conversion failed: {e}") from e

        for i, image in enumerate(images):
            try:
                text = pytesseract.image_to_string(image, lang=lang)
                data = pytesseract.image_to_data(image, lang=lang, output_type=pytesseract.Output.DICT)

                # Compute average confidence
                confidences = [int(c) for c in data.get("conf", []) if int(c) > 0]
                avg_conf = sum(confidences) / len(confidences) if confidences else 0

                pages_data.append({
                    "page": i + 1,
                    "text": text.strip(),
                    "confidence": round(avg_conf, 1),
                    "char_count": len(text.strip()),
                })
                all_text.append(text.strip())
            except Exception as e:
                logger.warning("OCR failed for page %d: %s", i + 1, e)
                pages_data.append({
                    "page": i + 1,
                    "text": "",
                    "confidence": 0.0,
                    "error": str(e),
                })

        full_text = "\n\n--- PAGE BREAK ---\n\n".join(all_text)
        avg_confidence = (
            sum(p["confidence"] for p in pages_data) / len(pages_data)
            if pages_data else 0
        )

        return OCRResult(
            text=full_text,
            confidence=round(avg_confidence, 1),
            page_count=len(pages_data),
            pages=pages_data,
            source_path=str(file_path),
            correlation_id=correlation_id,
            language=lang,
        )

    # ── Process Image ─────────────────────────────────────────────────────

    def _process_image(
        self, file_path: Path, lang: str, correlation_id: str
    ) -> OCRResult:
        """Process a single image file."""
        import pytesseract

        try:
            from PIL import Image
            image = Image.open(str(file_path))
        except Exception as e:
            raise ValueError(f"Failed to open image: {e}") from e

        try:
            text = pytesseract.image_to_string(image, lang=lang)
            data = pytesseract.image_to_data(image, lang=lang, output_type=pytesseract.Output.DICT)

            confidences = [int(c) for c in data.get("conf", []) if int(c) > 0]
            avg_conf = sum(confidences) / len(confidences) if confidences else 0

            return OCRResult(
                text=text.strip(),
                confidence=round(avg_conf, 1),
                page_count=1,
                pages=[{
                    "page": 1,
                    "text": text.strip(),
                    "confidence": round(avg_conf, 1),
                    "char_count": len(text.strip()),
                }],
                source_path=str(file_path),
                correlation_id=correlation_id,
                language=lang,
            )
        except Exception as e:
            raise ValueError(f"OCR processing failed: {e}") from e

    # ── Status ────────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        """Get OCR service status and capability info."""
        return {
            "tesseract_available": self._tesseract_available,
            "pytesseract_available": self._pytesseract_available,
            "pdf2image_available": self._pdf2image_available,
            "language": self._tesseract_lang,
            "supported_extensions": sorted(self.SUPPORTED_EXTENSIONS),
            "max_file_size_mb": self.MAX_FILE_SIZE // (1024 * 1024),
        }
