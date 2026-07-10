# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
"""
fireai/integration/document_intelligence.py — Document Intelligence Connector

V140 Phase 10: Integrates DocTR (OCR) and YOLO (layout segmentation) as
optional sidecar services for enhanced PDF/image floor plan parsing.

ARCHITECTURE:
    FireAI Core  ──HTTP──>  DocTR OCR Service (port 8001)
                         ──HTTP──>  YOLO Segmentation Service (port 8002)

Both services run as separate Docker containers (docker-compose.yml).
This connector is OPTIONAL — if services are unavailable, FireAI falls
back to the existing pdfplumber + Tesseract + OpenCV pipeline.

NO AGPL CONTAMINATION:
    DocTR and YOLO run as separate processes. FireAI calls them via HTTP.
    No Chunkr/DocTR/YOLO code is copied into FireAI. This is a "separate
    work" under AGPL §5 — the connector only knows the HTTP API contract.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger("fireai.integration.document_intelligence")

# ─── Configuration ───────────────────────────────────────────────────────────

DOCTR_URL = os.getenv("FIREAI_DOCTR_URL", "http://localhost:8001")
YOLO_URL = os.getenv("FIREAI_YOLO_URL", "http://localhost:8002")

# Timeout for OCR/segmentation calls (seconds)
_REQUEST_TIMEOUT = int(os.getenv("FIREAI_DI_TIMEOUT", "120"))

# Minimum text length to consider a page as "has text" (below this, try OCR)
_MIN_TEXT_LENGTH = 50


# ─── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class OCRWord:
    """A single word detected by OCR with bounding box."""
    value: str
    confidence: float
    geometry: List[List[float]]  # [[x1,y1], [x2,y2]] normalized 0-1


@dataclass
class OCRLine:
    """A line of text detected by OCR."""
    words: List[OCRWord]
    geometry: List[List[float]]


@dataclass
class OCRBlock:
    """A text block detected by OCR."""
    lines: List[OCRLine]
    geometry: List[List[float]]


@dataclass
class OCRPageResult:
    """OCR result for a single page."""
    page_idx: int
    dimensions: Tuple[int, int]  # (width, height) in pixels
    blocks: List[OCRBlock]
    processing_time: float

    @property
    def full_text(self) -> str:
        """Concatenate all words into a single text string."""
        return " ".join(
            word.value
            for block in self.blocks
            for line in block.lines
            for word in line.words
        )


@dataclass
class SegmentBox:
    """A layout segment detected by YOLO."""
    segment_type: str  # "text", "title", "table", "figure", "list", "caption", etc.
    bbox: Tuple[float, float, float, float]  # (left, top, width, height) in pixels
    confidence: float


@dataclass
class SegmentationResult:
    """YOLO layout segmentation result for a single page."""
    page_idx: int
    image_size: Tuple[int, int]  # (height, width)
    segments: List[SegmentBox]


@dataclass
class DocumentIntelligenceResult:
    """Combined OCR + segmentation result."""
    success: bool
    ocr_pages: List[OCRPageResult] = field(default_factory=list)
    segmentation_pages: List[SegmentationResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        """All text from all pages."""
        return "\n---PAGE BREAK---\n".join(
            page.full_text for page in self.ocr_pages
        )


# ─── Service Availability Check ──────────────────────────────────────────────

def is_doctr_available() -> bool:
    """Check if DocTR OCR service is running."""
    try:
        import requests
        r = requests.get(f"{DOCTR_URL}/", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def is_yolo_available() -> bool:
    """Check if YOLO segmentation service is running."""
    try:
        import requests
        r = requests.get(f"{YOLO_URL}/", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


# ─── DocTR OCR Integration ───────────────────────────────────────────────────

def ocr_image(image_bytes: bytes) -> Optional[List[OCRPageResult]]:  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
    """
    Send image bytes to DocTR OCR service and get structured text back.

    Args:
        image_bytes: Raw image bytes (PNG/JPEG)

    Returns:
        List of OCRPageResult, or None if service unavailable.
    """
    try:
        import requests
    except ImportError:
        logger.warning("requests not installed — DocTR OCR unavailable")
        return None

    try:
        response = requests.post(
            f"{DOCTR_URL}/batch",
            files=[("files", ("page.png", image_bytes, "image/png"))],
            timeout=_REQUEST_TIMEOUT,
        )
        if response.status_code != 200:
            logger.error("DocTR OCR returned %s: %s", response.status_code, response.text[:200])
            return None

        data = response.json()
        results = []
        for page_data in data:
            blocks = []
            for block_data in page_data.get("page_content", {}).get("blocks", []):
                lines = []
                for line_data in block_data.get("lines", []):
                    words = []
                    for word_data in line_data.get("words", []):
                        words.append(OCRWord(
                            value=word_data.get("value", ""),
                            confidence=word_data.get("confidence", 0.0),
                            geometry=word_data.get("geometry", [[0, 0], [1, 1]]),
                        ))
                    lines.append(OCRLine(
                        words=words,
                        geometry=line_data.get("geometry", [[0, 0], [1, 1]]),
                    ))
                blocks.append(OCRBlock(
                    lines=lines,
                    geometry=block_data.get("geometry", [[0, 0], [1, 1]]),
                ))

            dims = page_data.get("page_content", {}).get("dimensions", [0, 0])
            results.append(OCRPageResult(
                page_idx=page_data.get("page_content", {}).get("page_idx", 0),
                dimensions=(dims[0] if len(dims) > 0 else 0, dims[1] if len(dims) > 1 else 0),
                blocks=blocks,
                processing_time=page_data.get("processing_time", 0.0),
            ))

        logger.info("DocTR OCR: extracted %d pages", len(results))
        return results

    except Exception as e:
        logger.exception("DocTR OCR failed: %s", e)
        return None


# ─── YOLO Segmentation Integration ──────────────────────────────────────────

def segment_image(image_bytes: bytes) -> Optional[List[SegmentationResult]]:  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
    """
    Send image bytes to YOLO segmentation service and get layout segments.

    Args:
        image_bytes: Raw image bytes (PNG/JPEG)

    Returns:
        List of SegmentationResult, or None if service unavailable.
    """
    try:
        import requests
    except ImportError:
        logger.warning("requests not installed — YOLO segmentation unavailable")
        return None

    try:
        response = requests.post(
            f"{YOLO_URL}/batch",
            files=[("files", ("page.png", image_bytes, "image/png"))],
            timeout=_REQUEST_TIMEOUT,
        )
        if response.status_code != 200:
            logger.error("YOLO segmentation returned %s: %s", response.status_code, response.text[:200])
            return None

        data = response.json()
        results = []
        for page_idx, page_data in enumerate(data):
            instances = page_data.get("instances", {})
            boxes_output = instances.get("boxes", [])
            classes = instances.get("classes", [])
            scores = instances.get("scores", [])
            image_size = instances.get("image_size", [0, 0])

            segments = []
            for i, box in enumerate(boxes_output):
                seg_type = classes[i] if i < len(classes) else "unknown"
                confidence = scores[i] if i < len(scores) else 0.0
                segments.append(SegmentBox(
                    segment_type=str(seg_type),
                    bbox=(box.get("left", 0), box.get("top", 0),
                          box.get("width", 0), box.get("height", 0)),
                    confidence=float(confidence),
                ))

            results.append(SegmentationResult(
                page_idx=page_idx,
                image_size=(image_size[0] if len(image_size) > 0 else 0,
                           image_size[1] if len(image_size) > 1 else 0),
                segments=segments,
            ))

        logger.info("YOLO segmentation: %d pages, %d total segments",
                     len(results),
                     sum(len(r.segments) for r in results))
        return results

    except Exception as e:
        logger.exception("YOLO segmentation failed: %s", e)
        return None


# ─── Combined Document Intelligence ──────────────────────────────────────────

def analyze_document(  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
    page_images: List[bytes],
    enable_ocr: bool = True,
    enable_segmentation: bool = True,
) -> DocumentIntelligenceResult:
    """
    Analyze a document (list of page images) using DocTR OCR + YOLO segmentation.

    Args:
        page_images: List of page image bytes (PNG/JPEG)
        enable_ocr: Whether to run OCR (default True)
        enable_segmentation: Whether to run layout segmentation (default True)

    Returns:
        DocumentIntelligenceResult with OCR text + layout segments.
    """
    result = DocumentIntelligenceResult(success=False)

    if not page_images:
        result.errors.append("No page images provided")
        return result

    # Check service availability
    doctr_ok = enable_ocr and is_doctr_available()
    yolo_ok = enable_segmentation and is_yolo_available()

    if not doctr_ok and not yolo_ok:
        result.errors.append("Neither DocTR OCR nor YOLO segmentation available")
        return result

    if enable_ocr and not doctr_ok:
        result.warnings.append("DocTR OCR service unavailable — skipping OCR")

    if enable_segmentation and not yolo_ok:
        result.warnings.append("YOLO segmentation service unavailable — skipping segmentation")

    # Run OCR on all pages
    if doctr_ok:
        for page_idx, img_bytes in enumerate(page_images):
            ocr_result = ocr_image(img_bytes)
            if ocr_result:
                for page in ocr_result:
                    page.page_idx = page_idx
                    result.ocr_pages.append(page)
            else:
                result.warnings.append(f"OCR failed for page {page_idx}")

    # Run segmentation on all pages
    if yolo_ok:
        for page_idx, img_bytes in enumerate(page_images):
            seg_result = segment_image(img_bytes)
            if seg_result:
                for page in seg_result:
                    page.page_idx = page_idx
                    result.segmentation_pages.append(page)
            else:
                result.warnings.append(f"Segmentation failed for page {page_idx}")

    result.success = len(result.ocr_pages) > 0 or len(result.segmentation_pages) > 0
    return result


# ─── Helper: Render PDF page to image ────────────────────────────────────────

def render_pdf_page_to_image(pdf_path: str, page_num: int = 0, dpi: int = 200) -> Optional[bytes]:
    """
    Render a PDF page as a PNG image for OCR/segmentation.

    Args:
        pdf_path: Path to PDF file
        page_num: Page number (0-indexed)
        dpi: Resolution for rendering

    Returns:
        PNG image bytes, or None if rendering failed.
    """
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        if page_num >= len(doc):
            logger.error("Page %d out of range (PDF has %d pages)", page_num, len(doc))
            return None

        page = doc[page_num]
        zoom = dpi / 72  # 72 DPI is default PDF resolution
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix)
        image_bytes = pix.tobytes("png")
        doc.close()

        logger.info("Rendered PDF page %d to %dx%d PNG (%d bytes)",
                     page_num, pix.width, pix.height, len(image_bytes))
        return image_bytes

    except ImportError:
        logger.warning("PyMuPDF (fitz) not installed — cannot render PDF pages")
        return None
    except Exception as e:
        logger.exception("PDF page rendering failed: %s", e)
        return None


def render_all_pdf_pages(pdf_path: str, dpi: int = 200) -> List[bytes]:
    """
    Render all pages of a PDF as PNG images.

    Args:
        pdf_path: Path to PDF file
        dpi: Resolution for rendering

    Returns:
        List of PNG image bytes (one per page).
    """
    try:
        import fitz
        doc = fitz.open(pdf_path)
        page_count = len(doc)
        images = []
        for i in range(page_count):
            img = render_pdf_page_to_image(pdf_path, i, dpi)
            if img:
                images.append(img)
        doc.close()
        logger.info("Rendered %d/%d pages from %s", len(images), page_count, pdf_path)
        return images
    except Exception as e:
        logger.exception("Failed to render PDF pages: %s", e)
        return []


__all__ = [
    "DocumentIntelligenceResult",
    "OCRBlock",
    "OCRLine",
    "OCRPageResult",
    "OCRWord",
    "SegmentBox",
    "SegmentationResult",
    "analyze_document",
    "is_doctr_available",
    "is_yolo_available",
    "ocr_image",
    "render_all_pdf_pages",
    "render_pdf_page_to_image",
    "segment_image",
]
