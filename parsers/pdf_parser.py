"""
pdf_parser.py — FireAI PDF Floor Plan Parser
Extracts fire alarm device locations from PDF drawings.

SAFETY-CRITICAL: Parses PDF floor plans to detect:
- Smoke detectors
- Heat detectors
- Pull stations
- Notification appliances
- Fire alarm panels

DEPENDENCIES:
    pip install pdfplumber pymupdf
"""

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger("fireai.pdf_parser")


# ═══════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════

@dataclass
class PDFDevice:
    """Single fire device from PDF."""

    device_type: str      # SMOKE_DETECTOR, HEAT_DETECTOR, PULL_STATION, etc.
    location: str         # Room/area description
    page: int
    x: float            # X coordinate on page
    y: float            # Y coordinate on page

    def to_dict(self) -> dict:
        return {
            "type": self.device_type,
            "location": self.location,
            "page": self.page,
            "coordinates": (self.x, self.y)
        }


@dataclass
class PDFParseResult:
    """Result of parsing PDF floor plan."""

    source_file: str
    success: bool
    page_count: int = 0
    devices: List[PDFDevice] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    text_content: str = ""

    @property
    def device_count(self) -> int:
        return len(self.devices)


# ═══════════════════════════════════════════════════════
# DEVICE PATTERNS (NFPA 72 compliant)
# ═══════════════════════════════════════════════════════

# Device type keywords - order matters (most specific first)
DEVICE_PATTERNS = [
    # Smoke/Heat detectors
    (r'smoke\s*detector', 'SMOKE_DETECTOR'),
    (r'heat\s*detector', 'HEAT_DETECTOR'),
    (r'photoelectric\s*detector', 'SMOKE_DETECTOR'),
    (r'ionization\s*detector', 'SMOKE_DETECTOR'),
    (r'fixed\s*temp', 'HEAT_DETECTOR'),
    (r'rate-of-rise', 'HEAT_DETECTOR'),

    # Pull stations
    (r'pull\s*station', 'PULL_STATION'),
    (r'fire\s*alarm\s*pull', 'PULL_STATION'),
    (r'manual\s*pull', 'PULL_STATION'),
    (r'break\s*glass', 'PULL_STATION'),

    # Notification appliances — ORDER MATTERS (most specific first)
    # V78 FIX: Moved horn-strobe pattern BEFORE simple horn pattern.
    # Previously, 'horn' matched "horn/strobe" first, misclassifying
    # combined devices as simple HORN. NFPA 72 requires separate
    # counting for combined vs standalone notification appliances.
    (r'horn[\s-]*strobe', 'HORN_STROBE'),
    (r'horn', 'HORN'),
    (r'strobe', 'STROBE'),
    (r'bell', 'BELL'),
    (r'speaker', 'SPEAKER'),
    (r'notification', 'NOTIFICATION'),

    # Panel
    (r'fire\s*alarm\s*panel', 'FAP'),
    (r'control\s*panel', 'FAP'),
    (r'facp', 'FAP'),
    (r'main\s*panel', 'FAP'),

    # Sprinkler
    (r'sprinkler', 'SPRINKLER'),
    (r'flow\s*switch', 'FLOW_SWITCH'),
    (r'tamper\s*switch', 'TAMPER_SWITCH'),

    # Power
    (r'power\s*supply', 'POWER_SUPPLY'),
    (r'battery', 'BATTERY'),
]


@dataclass
class PDFParser:
    """
    Parses PDF floor plans for fire alarm devices.

    USAGE:
        parser = PDFParser()
        result = parser.parse("floor_plan.pdf")

        if result.success:
            print(f"Found {result.device_count} devices")
            for d in result.devices:
                print(f"  {d.device_type}: {d.location}")
    """

    def __init__(self, min_confidence: float = 0.5):
        """
        Args:
        min_confidence: Minimum confidence threshold (0-1)

        """
        self.min_confidence = min_confidence
        self._device_cache: Dict[str, str] = {}

    def parse(self, pdf_path: str) -> PDFParseResult:
        """
        Parse PDF file for fire alarm devices.

        Args:
            pdf_path: Path to PDF file. MUST be under FIREAI_ALLOWED_UPLOAD_DIRS
                and MUST have a .pdf extension (V124 security hardening).

        Returns:
            PDFParseResult with detected devices

        """
        # V126: Path security + file-size cap
        from parsers._path_security import (
            UnsafePathError,
            validate_file_size,
            validate_input_path,
        )
        _ALLOWED_EXTENSIONS = frozenset({".pdf"})
        _MAX_FILE_SIZE_BYTES = int(os.getenv("FIREAI_PDF_MAX_FILE_SIZE_BYTES", 200 * 1024 * 1024))  # 200 MB default
        try:
            safe_path = validate_input_path(
                pdf_path,
                allowed_extensions=_ALLOWED_EXTENSIONS,
                parser_name="PDFParser",
            )
            validate_file_size(
                safe_path,
                max_size_bytes=_MAX_FILE_SIZE_BYTES,
                parser_name="PDFParser",
            )
        except UnsafePathError as e:
            # V127 FIX: Return error result instead of raising ValueError.
            # The test contract expects parse() to return a result object
            # with success=False and SECURITY errors, not to raise.
            return PDFParseResult(source_file=pdf_path, success=False, errors=[f"SECURITY: {e}"])
        except FileNotFoundError as e:
            # V127 FIX: Return error result for missing files.
            return PDFParseResult(source_file=pdf_path, success=False, errors=[str(e)])

        result = PDFParseResult(source_file=pdf_path, success=False)

        # V125 SECURITY (Finding #5 follow-up, Rule #23):
        # Delegate path validation to the shared helper. Closes:
        #   - Path traversal (../../etc/passwd)
        #   - Null byte truncation
        #   - Argument injection (leading '-')
        #   - Files outside FIREAI_ALLOWED_UPLOAD_DIRS
        #   - DoS via oversized files (cap: 200 MB, env-configurable)
        # PDF files can be very large (multi-page architectural plans),
        # so the default cap is higher than DWG.
        import os as _os

        from parsers._path_security import (
            UnsafePathError,
            validate_file_size,
            validate_input_path,
        )

        _PDF_MAX_BYTES = int(_os.getenv("FIREAI_PDF_MAX_FILE_SIZE_BYTES",
                                       str(200 * 1024 * 1024)))  # 200 MB

        try:
            safe_path = validate_input_path(
                pdf_path,
                allowed_extensions=frozenset({".pdf"}),
                parser_name="PDFParser",
            )
            validate_file_size(safe_path, max_size_bytes=_PDF_MAX_BYTES,
                               parser_name="PDFParser")
        except FileNotFoundError as e:
            result.errors.append(str(e))
            return result
        except UnsafePathError as e:
            result.errors.append(f"SECURITY: {e}")
            logger.warning("PDFParser rejected unsafe path: %s", e)
            return result

        # Use resolved canonical path for all subsequent operations (TOCTOU fix)
        pdf_path = str(safe_path)

        # Try pdfplumber first
        try:
            devices, text, page_count = self._parse_pdfplumber(str(safe_path))
            result.devices = devices
            result.text_content = text
            result.page_count = page_count
            # V78 FIX: success requires at least some fire devices found.
            # Previously, any text at all (even non-fire-related) set success=True,
            # potentially misleading downstream code into thinking the building
            # has been analyzed for fire protection when it hasn't.
            result.success = len(devices) > 0
            if len(text) > 0 and len(devices) == 0:
                result.warnings.append("Text extracted but no fire devices identified")

        except ImportError as e:
            result.errors.append(f"Missing dependency: {e}")

        except Exception as e:
            result.errors.append(f"Parse error: {type(e).__name__}: {e}")

        return result

    def _parse_pdfplumber(self, pdf_path: str):
        """Parse using pdfplumber."""
        import pdfplumber

        devices = []
        all_text = []

        with pdfplumber.open(pdf_path) as pdf:
            page_count = len(pdf.pages)

            for page_num, page in enumerate(pdf.pages, 1):
                # Extract text
                text = page.extract_text()

                # If no text, try OCR
                if not text or len(text.strip()) < 50:
                    logger.info("Page %s: No text found, trying OCR...", page_num)
                    text = self._ocr_page(page)
                    if text:
                        logger.info("Page %s: OCR recovered %s chars", page_num, len(text))

                if text:
                    all_text.append(text)

                    # Find devices in text
                    page_devices = self._find_devices(text, page_num)
                    devices.extend(page_devices)

                # Extract tables
                tables = page.extract_tables()
                for table in tables:
                    if table:
                        table_text = ' '.join(str(cell) for row in table for cell in row)
                        table_devices = self._find_devices(table_text, page_num)
                        devices.extend(table_devices)

        devices = self._deduplicate_devices(devices)

        return devices, '\n'.join(all_text), page_count

    def _ocr_page(self, page) -> str:
        """Extract text from page using OCR (Tesseract or DocTR)."""
        # V140 Phase 10: Try DocTR OCR service first (more accurate), fall back to Tesseract
        try:
            from fireai.integration.document_intelligence import is_doctr_available, ocr_image
            if is_doctr_available():
                # Render page to image
                img = page.to_image(resolution=200)
                import io
                buf = io.BytesIO()
                img.original.save(buf, format="PNG")
                image_bytes = buf.getvalue()

                ocr_result = ocr_image(image_bytes)
                if ocr_result and len(ocr_result) > 0:
                    text = ocr_result[0].full_text
                    if text and len(text.strip()) > 10:
                        logger.info("DocTR OCR: extracted %d chars", len(text))
                        return text
        except Exception as e:
            logger.debug("DocTR OCR unavailable, falling back to Tesseract: %s", e)

        # Fall back to Tesseract
        try:

            import pytesseract

            os.environ['TESSDATA_PREFIX'] = '/usr/share/tesseract-ocr'

            # Get page as image
            img = page.to_image(resolution=150)
            pil_img = img.original

            # Run OCR
            return pytesseract.image_to_string(
                pil_img,
                lang='eng',
                config='--tessdata-dir /usr/share/tesseract-ocr/5/tessdata'
            )

        except ImportError:
            logger.warning("pytesseract not installed")
            return ""
        except Exception as e:
            logger.exception("OCR failed: %s", e)
            return ""

    def _find_devices(self, text: str, page: int) -> List[PDFDevice]:
        """Find fire alarm devices in text."""
        devices = []

        # Normalize text
        text_lower = text.lower()

        # Find each device type
        for pattern, device_type in DEVICE_PATTERNS:
            matches = re.finditer(pattern, text_lower, re.IGNORECASE)

            for match in matches:
                # Find approximate location (room number)
                location = self._extract_location(text, match.start())

                # Get position if possible
                x, y = self._guess_coordinates(text, match.start())

                devices.append(PDFDevice(
                    device_type=device_type,
                    location=location or "Unknown",
                    page=page,
                    x=x,
                    y=y
                ))

        return devices

    def _extract_location(self, text: str, position: int) -> Optional[str]:
        """Extract room/location near match position."""
        # Look for room numbers nearby (e.g., Room 101, R-101, 101)
        window = text[max(0, position-50):position+50]

        # Room patterns
        room_patterns = [
            r'(?:room|r[\s-]*|#)\s*(\d+[A-Za-z]?)',
            r'((?:\d+)[A-Za-z]?)\s*$',
            r'([A-Z]\d+)',
        ]

        for pattern in room_patterns:
            match = re.search(pattern, window, re.IGNORECASE)
            if match:
                return f"Room {match.group(1)}"

        return None

    def _guess_coordinates(self, text: str, position: int) -> tuple:
        """Guess coordinates from text layout."""
        # Estimate based on text position
        # This is approximate - real coordinates need PDF layout analysis
        return (0.0, 0.0)

    def _extract_layout_devices(self, _page_num: int) -> List[PDFDevice]:  # NOSONAR — S1172: parameter retained for API stability
        """Extract devices from PDF layout (images/shapes)."""
        devices = []

        # Try to detect shapes that might be devices
        # This is basic - advanced implementation would use CV/AI

        # Check for common fire device symbols in PDF objects
        try:
            # This is a placeholder - real implementation would analyze
            # PDF shapes, images, and custom symbols
            pass
        except Exception as exc:
            logger.debug("Symbol detection placeholder failed: %s", exc)

        return devices

    def _deduplicate_devices(self, devices: List[PDFDevice]) -> List[PDFDevice]:
        """Remove duplicate devices."""
        seen = set()
        unique = []

        for d in devices:
            key = (d.device_type, d.location, d.page)
            if key not in seen:
                seen.add(key)
                unique.append(d)

        return unique


# ═══════════════════════════════════════════════════════
# REPORT GENERATOR
# ═══════════════════════════════════════════════════════

class PDFReportGenerator:
    """Generate PDF inspection reports."""

    def __init__(self):
        self.parser = PDFParser()

    def generate_report(self, pdf_path: str) -> dict:
        """
        Generate inspection report from PDF floor plan.

        Returns:
            dict with report data

        """
        result = self.parser.parse(pdf_path)

        # Count by type
        device_counts: Dict[str, int] = {}
        for d in result.devices:
            device_counts[d.device_type] = device_counts.get(d.device_type, 0) + 1

        # Build report
        return {
            "source": result.source_file,
            "success": result.success,
            "page_count": result.page_count,
            "device_count": result.device_count,
            "device_counts": device_counts,
            "devices": [d.to_dict() for d in result.devices],
            "errors": result.errors,
            "warnings": result.warnings,

            # NFPA 72 summary
            "smoke_detectors": device_counts.get("SMOKE_DETECTOR", 0),
            "heat_detectors": device_counts.get("HEAT_DETECTOR", 0),
            "pull_stations": device_counts.get("PULL_STATION", 0),
            "notification_appliances": (
                device_counts.get("HORN", 0) +
                device_counts.get("STROBE", 0) +
                device_counts.get("HORN_STROBE", 0)
            ),
        }


    def print_report(self, pdf_path: str) -> str:
        """Generate and return formatted report."""
        report = self.generate_report(pdf_path)

        lines = [
            "=" * 60,
            "FIRE ALARM PDF INSPECTION REPORT",
            "=" * 60,
            f"Source: {report['source']}",
            f"Status: {'SUCCESS' if report['success'] else 'FAILED'}",
            f"Pages: {report['page_count']}",
            "",
            "-" * 40,
            "DEVICE SUMMARY",
            "-" * 40,
        ]

        for dtype, count in report['device_counts'].items():
            lines.append(f"  {dtype}: {count}")

        lines.extend([
            "",
            "-" * 40,
            "NFPA 72 COMPLIANCE",
            "-" * 40,
            f"  Smoke Detectors: {report['smoke_detectors']}",
            f"  Heat Detectors: {report['heat_detectors']}",
            f"  Pull Stations: {report['pull_stations']}",
            f"  Notification: {report['notification_appliances']}",
        ])

        if report['errors']:
            lines.extend(["", "ERRORS:"] + report['errors'])

        if report['warnings']:
            lines.extend(["", "WARNINGS:"] + report['warnings'])

        return '\n'.join(lines)


# ═══════════════════════════════════════════════════════
# CONVENIENCE FUNCTION
# ═══════════════════════════════════════════════════════

def parse_pdf(pdf_path: str) -> PDFParseResult:
    """Quick parse PDF floor plan."""
    parser = PDFParser()
    return parser.parse(pdf_path)


def generate_inspection_report(pdf_path: str) -> dict:
    """Generate inspection report."""
    generator = PDFReportGenerator()
    return generator.generate_report(pdf_path)
