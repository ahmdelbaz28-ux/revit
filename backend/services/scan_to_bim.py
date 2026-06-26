"""
backend/services/scan_to_bim.py — Scanned PDF/Plan → BIM Extraction
====================================================================

Converts OCR text from scanned architectural drawings into structured
BIM-like data (rooms, walls, areas) for NFPA analysis pipeline.

Pipeline: Scanned PDF → OCR → Text Analysis → Rooms/Walls → NFPA

SAFETY-CRITICAL:
  - Extraction is BEST-EFFORT — always flag for human verification
  - Missing rooms = zero fire protection — must be flagged
  - Low confidence results are never silently accepted
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from backend.services.ocr_service import OCRService

logger = logging.getLogger("fireai.services.scan_to_bim")


@dataclass
class ExtractedRoom:
    """A room extracted from OCR text."""
    name: str
    area: float
    unit: str = "sqm"
    confidence: float = 0.0
    page: int = 1
    raw_text: str = ""


@dataclass
class ScanToBIMResult:
    """Complete result of scanned plan → BIM extraction."""
    rooms: list[ExtractedRoom] = field(default_factory=list)
    total_area: float = 0.0
    ocr_confidence: float = 0.0
    source_path: str = ""
    correlation_id: str = ""
    requires_human_review: bool = True  # Always true — OCR is never 100%
    warnings: list[str] = field(default_factory=list)
    extracted_at: str = ""

    def __post_init__(self):
        """Auto-set extracted_at timestamp if not already provided."""
        if not self.extracted_at:
            self.extracted_at = datetime.now(timezone.utc).isoformat()


class ScanToBIMService:
    """
    Convert scanned architectural plans to BIM-like structure.

    Uses OCR to extract text, then pattern matching to identify
    rooms, areas, and spatial information.
    """

    # Patterns for extracting room data from OCR text
    ROOM_PATTERNS = [
        # "Room 101" / "Room-101" / "Rm 101"
        re.compile(r"(?:Room|Rm\.?)\s*[-]?\s*(\w+)", re.IGNORECASE),
        # "Office" / "Corridor" / "Kitchen" etc.
        re.compile(r"\b(Office|Corridor|Kitchen|Bedroom|Bathroom|Lobby|Hall|Stair|Storage|Utility|Classroom|Lab|Workshop|Meeting|Conference)\b", re.IGNORECASE),
    ]

    AREA_PATTERNS = [
        # "25.5 sqm" / "25.5 m2" / "25.5 sq.m"
        re.compile(r"(\d+\.?\d*)\s*(?:sqm|m2|sq\.?\s*m|m²)", re.IGNORECASE),
        # "Area: 25.5" / "Area = 25.5"
        re.compile(r"Area\s*[:=]\s*(\d+\.?\d*)", re.IGNORECASE),
    ]

    def __init__(self):
        """Initialize the service with an OCR backend for text extraction."""
        self._ocr_service = OCRService()

    def process(
        self,
        file_path: str,
        correlation_id: str | None = None,
    ) -> ScanToBIMResult:
        """
        Process a scanned plan file: OCR → extract rooms/walls.

        Args:
            file_path: Path to scanned PDF or image.
            correlation_id: Audit trail ID.

        Returns:
            ScanToBIMResult with extracted rooms and metadata.
        """
        if correlation_id is None:
            correlation_id = f"s2b-{uuid.uuid4().hex[:12]}"

        logger.info(
            "ScanToBIM processing | file=%s | correlation_id=%s",
            file_path, correlation_id,
        )

        # Step 1: OCR
        try:
            ocr_result = self._ocr_service.process(
                file_path, correlation_id=correlation_id
            )
        except ValueError as e:
            raise ValueError(f"OCR failed: {e}") from e

        # Step 2: Extract rooms from OCR text
        rooms = self._extract_rooms(ocr_result)

        # Step 3: Compute totals
        total_area = sum(r.area for r in rooms)
        warnings = []

        if not rooms:
            warnings.append("No rooms detected — manual review REQUIRED")

        if ocr_result.confidence < 50:
            warnings.append(
                f"Low OCR confidence ({ocr_result.confidence}%) — "
                "results may be inaccurate. Manual verification REQUIRED."
            )

        if total_area <= 0 and rooms:
            warnings.append(
                "Rooms detected but no areas extracted — "
                "manual area measurement REQUIRED."
            )

        result = ScanToBIMResult(
            rooms=rooms,
            total_area=total_area,
            ocr_confidence=ocr_result.confidence,
            source_path=file_path,
            correlation_id=correlation_id,
            requires_human_review=True,  # Always — OCR is never 100%
            warnings=warnings,
        )

        logger.info(
            "ScanToBIM complete | rooms=%d | area=%.1f | confidence=%.1f | warnings=%d",
            len(rooms), total_area, ocr_result.confidence, len(warnings),
        )

        return result

    def _extract_rooms(self, ocr_result) -> list[ExtractedRoom]:
        """Extract room data from OCR text using pattern matching."""
        rooms: list[ExtractedRoom] = []
        seen_names: set[str] = set()

        for page_data in ocr_result.pages:
            text = page_data.get("text", "")
            page_num = page_data.get("page", 1)
            conf = page_data.get("confidence", 0)

            if not text.strip():
                continue

            # Find room names
            room_names = []
            for pattern in self.ROOM_PATTERNS:
                for match in pattern.finditer(text):
                    name = match.group(0).strip()
                    if name.lower() not in seen_names:
                        room_names.append(name)
                        seen_names.add(name.lower())

            # Find areas
            areas = []
            for pattern in self.AREA_PATTERNS:
                for match in pattern.finditer(text):
                    try:
                        area = float(match.group(1))
                        if area > 0:
                            areas.append(area)
                    except ValueError:
                        continue

            # Pair rooms with areas (best-effort)
            for i, name in enumerate(room_names):
                area = areas[i] if i < len(areas) else 0.0
                rooms.append(ExtractedRoom(
                    name=name,
                    area=area,
                    confidence=conf,
                    page=page_num,
                    raw_text=text[:200],
                ))

        return rooms
