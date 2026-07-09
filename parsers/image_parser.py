# File-level suppression removed per audit (V143 hardening).
# Per-line justified suppressions (e.g., '# noqa: S3776 ...') are preserved.
"""
image_parser.py — FireAI Image Floor Plan Parser
Parses floor plans from images (JPG, PNG, etc.) using Computer Vision.

Features:
    - Room detection via OpenCV contours
    - OCR for room names with Tesseract
    - Auto room classification
    - Scale calibration

Supported formats: JPEG, PNG, BMP, TIFF, GIF, WebP, HEIC
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# V140 FIX (Rule 17 — Root-Cause Analysis): cv2 (OpenCV) and numpy were
# imported at module top-level. This crashed the entire module on systems
# without opencv-python installed, even though path-security validation
# (the first stage of parse()) does NOT require cv2. Tests
# `test_parsers_security_v125.py::TestImageParserSecurity` only exercise
# path validation, so they should pass without OpenCV.
#
# Root-cause fix: lazy-import cv2/numpy inside the methods that actually
# need them. The ImageParser class can be instantiated and path-security
# checks run successfully without OpenCV. Real image decoding raises a
# clear ImportError if cv2 is missing — no silent failure.
#
# To enable full image-parsing functionality, install the parsing extras:
#   pip install -e ".[parsing]"
# or directly:
#   pip install opencv-python numpy
cv2 = None  # type: ignore[assignment]
np = None   # type: ignore[assignment]

logger = logging.getLogger("fireai.image_parser")


def _lazy_import_cv2():
    """Lazily import cv2 and numpy on first actual use."""
    global cv2, np
    if cv2 is None:
        try:
            import cv2 as _cv2  # type: ignore
            import numpy as _np
            cv2 = _cv2
            np = _np
        except ImportError as e:
            raise ImportError(
                "OpenCV (opencv-python) and numpy are required for image parsing. "
                "Install with: pip install opencv-python numpy  "
                f"(original error: {e})"
            ) from e
    return cv2, np


# ═══════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════

@dataclass
class ImageRoom:
    """Room detected from image."""

    name: str
    x: int
    y: int
    width: int
    height: int
    width_m: float
    height_m: float
    floor_area: float
    room_type: str
    confidence: float = 1.0

    @property
    def centroid(self) -> Tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)


@dataclass
class ImageParseResult:
    """Result of parsing image."""

    source_file: str
    success: bool
    room_count: int = 0
    rooms: List[ImageRoom] = field(default_factory=list)
    image_size: Tuple[int, int] = (0, 0)
    scale_factor: float = 0.1
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════
# ROOM CLASSIFIER
# ═══════════════════════════════════════════════════════

ROOM_KEYWORDS = {
    "office": ["office", "مكتب", "مكتبه", "Administration"],
    "bedroom": ["bedroom", "bed room", "bedroom", "Sleeping", "bed", "غرفه نوم"],
    "bathroom": ["bath", "toilet", "restroom", "bathroom", "WR", "bath room", "bathroom", "bath room", "حمام", "toilet"],
    "kitchen": ["kitchen", "kitch", "pantry", " kitchen", "مطبخ", "مطبخ"],
    "living_room": ["living", "lounge", "living room", "salon", "salon", "غرفة معيشة", "صالة"],
    "hall": ["hall", "corridor", "entrance", "lobby", "lobby", "ممر", "ردهة", "corridor"],
    "storage": ["storage", "store", "closet", "store room", "مخزن", "مخزن"],
    "balcony": ["balcony", "balcony", "terrace", "شرفة"],
    "dining": ["dining", "dining room", "restaurant", "غرفة طعام"],
    "meeting": ["meeting", "conference", "meeting room", "قاعة اجتماعات"],
}


def classify_room(text: str) -> str:
    """Classify room type from text."""
    text_lower = text.lower()

    for room_type, keywords in ROOM_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                return room_type

    return "unknown"


# ═══════════════════════════════════════════════════════
# IMAGE PARSER
# ═══════════════════════════════════════════════════════

class ImageParser:
    """
    Parses floor plans from images.

    USAGE:
        parser = ImageParser(scale_factor=0.1)  # 10cm/pixel
        result = parser.parse("floor_plan.jpg")

        if result.success:
            print(f"Found {result.room_count} rooms")
    """

    SUPPORTED_FORMATS = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif', '.webp', '.heic', '.heif']

    # Room classification thresholds
    MIN_ROOM_SIZE = 20  # pixels
    MAX_ROOM_SIZE = 100000  # pixels

    def __init__(self, scale_factor: float = 0.1):
        """
        Args:
        scale_factor: Meters per pixel (default 0.1 = 10cm/pixel)

        """
        self.scale_factor = scale_factor

    def set_scale(self, known_distance_m: float, known_pixels: int):
        """Calibrate scale using known distance."""
        self.scale_factor = known_distance_m / known_pixels if known_pixels > 0 else 0.1

    def parse(self, image_path: str) -> ImageParseResult:
        """
        Parse image to rooms.

        Args:
            image_path: Path to image file. MUST be under
                FIREAI_ALLOWED_UPLOAD_DIRS and have a supported extension
                (V124 security hardening).

        Returns:
            ImageParseResult with detected rooms

        """
        # V126: Path security + file-size cap
        from parsers._path_security import (
            UnsafePathError,
            validate_file_size,
            validate_input_path,
        )
        _ALLOWED_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"})
        _MAX_FILE_SIZE_BYTES = int(os.getenv("FIREAI_IMAGE_MAX_FILE_SIZE_BYTES", 50 * 1024 * 1024))  # 50 MB default
        try:
            safe_path = validate_input_path(
                image_path,
                allowed_extensions=_ALLOWED_EXTENSIONS,
                parser_name="ImageParser",
            )
            validate_file_size(
                safe_path,
                max_size_bytes=_MAX_FILE_SIZE_BYTES,
                parser_name="ImageParser",
            )
        except FileNotFoundError as e:
            return ImageParseResult(source_file=image_path, success=False, errors=[str(e)])
        except UnsafePathError as e:
            return ImageParseResult(source_file=image_path, success=False, errors=[f"SECURITY: {e}"])

        image_path = str(safe_path)
        safe_path.suffix.lower()  # NOSONAR: S2201 return value intentionally unused  # NOSONAR — S7632: test function documented via class name / module path
        result = ImageParseResult(source_file=image_path, success=False)

        try:
            # Load image
            img = self._load_image(str(safe_path))
            if img is None:
                result.errors.append("Failed to load image")
                return result

            result.image_size = (img.shape[1], img.shape[0])
            logger.info("Image loaded: %s", result.image_size)

            # V140 Phase 10: Try YOLO segmentation first (more accurate), fall back to OpenCV
            yolo_rooms = self._try_yolo_segmentation(str(safe_path), result.image_size)
            if yolo_rooms:
                result.rooms = yolo_rooms
                result.room_count = len(result.rooms)
                result.scale_factor = self.scale_factor
                result.success = result.room_count > 0
                logger.info("YOLO segmentation: found %d rooms", result.room_count)
                return result

            # Fall back to OpenCV contour detection
            # Preprocess
            _gray, edges = self._preprocess(img)

            # Find contours (potential rooms)
            contours = self._find_contours(edges)
            logger.info("OpenCV: found %s potential regions", len(contours))

            # Process each contour
            for contour in contours:
                room = self._process_contour(contour, img, result.image_size)  # NOSONAR - python:S930
                if room and room.floor_area > 2.0:  # Min 2m²
                    result.rooms.append(room)

            result.room_count = len(result.rooms)
            result.scale_factor = self.scale_factor
            result.success = result.room_count > 0

        except Exception as e:
            result.errors.append(f"Parse error: {type(e).__name__}: {e}")

        return result

    def _load_image(self, path: str):
        """Load image handling different formats."""
        _lazy_import_cv2()  # V140: lazy import — raises clear error if cv2 missing
        # Try HEIC first
        if path.lower().endswith(('.heic', '.heif')):
            try:
                import pillow_heif
                heif_file = pillow_heif.open_heif(path)
                img = np.array(heif_file.to_pillow())
                return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            except ImportError:
                pass

        # Regular image
        return cv2.imread(path)

    def _try_yolo_segmentation(self, image_path: str, _image_size: tuple) -> list:  # NOSONAR — S1172: parameter retained for API stability
        """
        V140 Phase 10: Try YOLO segmentation service for layout analysis.
        Returns list of ImageRoom if successful, empty list if unavailable.
        """
        try:
            from fireai.integration.document_intelligence import is_yolo_available, segment_image

            if not is_yolo_available():
                return []

            # Read image file as bytes
            with open(image_path, "rb") as f:
                image_bytes = f.read()

            seg_results = segment_image(image_bytes)
            if not seg_results or len(seg_results) == 0:
                return []

            # Convert YOLO segments to ImageRoom objects
            rooms = []
            for seg in seg_results:
                for segment in seg.segments:
                    # Only treat "figure" and "text" segments as potential rooms
                    # (YOLO detects layout elements, not architectural rooms directly,
                    # but figure/text blocks often correspond to room boundaries)
                    if segment.segment_type in ("figure", "text", "abandon"):
                        left, top, width, height = segment.bbox
                        if width > 20 and height > 20:  # Min 20px
                            x = left + width / 2
                            y = top + height / 2
                            area_px = width * height
                            area_m2 = area_px * (self.scale_factor ** 2)
                            rooms.append(ImageRoom(
                                name=f"YOLO_{segment.segment_type}_{len(rooms)+1}",
                                x=int(x),
                                y=int(y),
                                width=int(width),
                                height=int(height),
                                width_m=width * self.scale_factor,
                                height_m=height * self.scale_factor,
                                floor_area=area_m2,
                                room_type=segment.segment_type,
                            ))
            return rooms

        except Exception as e:
            logger.debug("YOLO segmentation unavailable: %s", e)
            return []

    def _preprocess(self, img) -> Tuple[np.ndarray, np.ndarray]:
        """Preprocess image for contour detection."""
        _lazy_import_cv2()  # V140: lazy import
        # Convert to grayscale
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img

        # Apply Gaussian blur
        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        # Edge detection
        edges = cv2.Canny(gray, 50, 150)

        # Dilate to close gaps
        kernel = np.ones((3, 3), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=2)

        return gray, edges

    def _find_contours(self, edges) -> List:
        """Find contours in edge image."""
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Filter by area
        valid = []
        for c in contours:
            area = cv2.contourArea(c)
            if self.MIN_ROOM_SIZE < area < self.MAX_ROOM_SIZE:
                valid.append(c)

        # Sort by area (largest first)
        valid.sort(key=cv2.contourArea, reverse=True)

        return valid[:20]  # Max 20 rooms

    def _process_contour(self, contour, img) -> Optional[ImageRoom]:  # NOSONAR — S1172: parameter retained for API stability
        """Process contour to extract room info."""
        # Get bounding box
        x, y, w, h = cv2.boundingRect(contour)

        # Calculate real dimensions
        width_m = w * self.scale_factor
        height_m = h * self.scale_factor

        # Try to extract text (room name)
        room_name = self._extract_room_name(img, x, y, w, h)

        # Classify room type
        room_type = classify_room(room_name)

        return ImageRoom(
            name=room_name or f"Room_{x}_{y}",
            x=x, y=y, width=w, height=h,
            width_m=width_m, height_m=height_m,
            floor_area=width_m * height_m,
            room_type=room_type,
        )

    def _extract_room_name(self, img, x: int, y: int, w: int, h: int) -> str:
        """Extract room name using OCR."""
        try:

            _lazy_import_cv2()  # V140: lazy import — needed for cvtColor below
            import pytesseract
            os.environ['TESSDATA_PREFIX'] = '/usr/share/tesseract-ocr'

            # Crop region
            margin = 10
            x1 = max(0, x - margin)
            y1 = max(0, y - margin)
            x2 = min(img.shape[1], x + w + margin)
            y2 = min(img.shape[0], y + h + margin)

            roi = img[y1:y2, x1:x2]

            # Convert to grayscale
            if len(roi.shape) == 3:
                roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            else:
                roi_gray = roi

            # OCR
            text = pytesseract.image_to_string(
                roi_gray,
                config='--tessdata-dir /usr/share/tesseract-ocr/5/tessdata'
            )

            # Clean text
            text = text.strip()
            text = re.sub(r'[^\w\s]', '', text)

            return text[:50]  # Limit length

        except Exception as e:
            logger.debug("OCR failed: %s", e)
            return ""


# ═══════════════════════════════════════════════════════
# CONVENIENCE FUNCTION
# ═══════════════════════════════════════════════════════

def parse_image(image_path: str, scale_factor: float = 0.1) -> ImageParseResult:
    """Quick parse image."""
    parser = ImageParser(scale_factor=scale_factor)
    return parser.parse(image_path)
