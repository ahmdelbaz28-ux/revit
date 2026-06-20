"""
FIREAI PDF INPUT LAYER — Real Drawing Parser
=====================================
الطبقة التي تربط البوابة بالمحرك.
تفتح PDF. تستخرج البيانات الحقيقية. تُمرر للمحرك فقط إن كان جديراً.

Author: The Eye That Refuses to Stay Closed
"""

import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

# Local imports
from parsers.parser_confidence import ConfidenceResult, GateDecision, ParserConfidence

logger = logging.getLogger("fireai.input_layer")


# ═══════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════

class DeviceType(Enum):
    """NFPA 170 device types."""
    SMOKE_DETECTOR = "SMOKE_DETECTOR"
    HEAT_DETECTOR = "HEAT_DETECTOR"
    PULL_STATION = "PULL_STATION"
    HORN = "HORN"
    STROBE = "STROBE"
    HORN_STROBE = "HORN_STROBE"
    SPEAKER = "SPEAKER"
    BELL = "BELL"
    NOTIFICATION_APPLIANCE = "NOTIFICATION_APPLIANCE"
    FIRE_ALARM_PANEL = "FIRE_ALARM_PANEL"
    POWER_SUPPLY = "POWER_SUPPLY"
    BATTERY = "BATTERY"
    SPRINKLER = "SPRINKLER"
    FLOW_SWITCH = "FLOW_SWITCH"
    TAMPER_SWITCH = "TAMPER_SWITCH"
    UNKNOWN = "UNKNOWN"


@dataclass
class ExtractedDevice:
    """Device extracted from PDF with real coordinates."""
    device_type: DeviceType
    x: float              # Real-world X (converted from page coords)
    y: float              # Real-world Y (converted from page coords)
    page: int
    room: Optional[str] = None
    zone: Optional[str] = None
    elevation: Optional[float] = None  # Ceiling height at this location
    confidence: float = 1.0

    def to_dict(self) -> dict:
        return {
            "type": self.device_type.value,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "page": self.page,
            "room": self.room,
            "zone": self.zone,
            "elevation": self.elevation,
            "confidence": self.confidence
        }


@dataclass
class RoomBoundary:
    """Room extracted from floor plan."""
    name: str              # Room number/name
    area_sqft: float       # Calculated area
    center_x: float
    center_y: float
    ceiling_height: float = 9.0  # Default feet
    boundary_points: List[Tuple[float, float]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "area_sqft": round(self.area_sqft, 2),
            "center_x": round(self.center_x, 2),
            "center_y": round(self.center_y, 2),
            "ceiling_height": self.ceiling_height,
            "boundary_points": [(round(x, 2), round(y, 2)) for x, y in self.boundary_points]
        }


@dataclass
class DrawingMetadata:
    """Metadata extracted from drawing."""
    building_name: Optional[str] = None
    floor_level: Optional[str] = None
    drawing_scale: Optional[str] = None
    date: Optional[str] = None
    designer: Optional[str] = None
    revision: Optional[str] = None
    north_arrow: bool = False

    def to_dict(self) -> dict:
        return {
            "building_name": self.building_name,
            "floor_level": self.floor_level,
            "drawing_scale": self.drawing_scale,
            "date": self.date,
            "designer": self.designer,
            "revision": self.revision,
            "north_arrow": self.north_arrow
        }


@dataclass
class InputLayerResult:
    """Result of input layer processing."""
    source_pdf: str
    confidence_result: ConfidenceResult
    devices: List[ExtractedDevice] = field(default_factory=list)
    rooms: List[RoomBoundary] = field(default_factory=list)
    metadata: Optional[DrawingMetadata] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def is_accepted(self) -> bool:
        """Was drawing accepted by confidence gate?"""
        return self.confidence_result.gate != GateDecision.REJECT

    @property
    def device_count(self) -> int:
        return len(self.devices)

    @property
    def room_count(self) -> int:
        return len(self.rooms)

    def to_engine_input(self) -> dict:
        """Convert to engine-compatible format."""
        return {
            "source_pdf": self.source_pdf,
            "accepted": self.is_accepted,
            "confidence": {
                "score": self.confidence_result.score,
                "gate": self.confidence_result.gate.value,
                "message": self.confidence_result.message
            },
            "devices": [d.to_dict() for d in self.devices],
            "rooms": [r.to_dict() for r in self.rooms],
            "metadata": self.metadata.to_dict() if self.metadata else {},
            "errors": self.errors,
            "warnings": self.warnings
        }


# ═══════════════════════════════════════════════════════
# NFPA 170 SYMBOL DEFINITIONS
# ═══════════════════════════════════════════════════════

NFPA_170_SYMBOLS = {
    # Smoke Detector
    "smoke": DeviceType.SMOKE_DETECTOR,
    "sd": DeviceType.SMOKE_DETECTOR,
    "smoke detector": DeviceType.SMOKE_DETECTOR,

    # Heat Detector
    "heat": DeviceType.HEAT_DETECTOR,
    "hd": DeviceType.HEAT_DETECTOR,
    "heat detector": DeviceType.HEAT_DETECTOR,
    "rate-of-rise": DeviceType.HEAT_DETECTOR,
    "fixed temp": DeviceType.HEAT_DETECTOR,

    # Pull Station
    "pull": DeviceType.PULL_STATION,
    "ps": DeviceType.PULL_STATION,
    "pull station": DeviceType.PULL_STATION,
    "manual pull": DeviceType.PULL_STATION,
    "break glass": DeviceType.PULL_STATION,

    # Notification
    "horn": DeviceType.HORN,
    "strobe": DeviceType.STROBE,
    "hs": DeviceType.HORN_STROBE,
    "horn/strobe": DeviceType.HORN_STROBE,
    "horn strobe": DeviceType.HORN_STROBE,
    "speaker": DeviceType.SPEAKER,
    "bell": DeviceType.BELL,

    # Panel
    "fap": DeviceType.FIRE_ALARM_PANEL,
    "panel": DeviceType.FIRE_ALARM_PANEL,
    "facp": DeviceType.FIRE_ALARM_PANEL,
    "fire alarm panel": DeviceType.FIRE_ALARM_PANEL,
    "control panel": DeviceType.FIRE_ALARM_PANEL,

    # Power
    "power": DeviceType.POWER_SUPPLY,
    "battery": DeviceType.BATTERY,

    # Sprinkler
    "sprinkler": DeviceType.SPRINKLER,
    "flow switch": DeviceType.FLOW_SWITCH,
    "tamper": DeviceType.TAMPER_SWITCH,
}


# ═══════════════════════════════════════════════════════
# MAIN INPUT LAYER
# ═══════════════════════════════════════════════════════

class PDFInputLayer:
    """
    الطبقة الحقيقية للمدخلات.

    1. يفتح PDF
    2. يمرر عبر بوابة الثقة
    3. يستخرج الأجهزة والإحداثيات
    4. يستخرج الغرف والارتفاعات
    5. يمرر للمحرك

    USAGE:
        layer = PDFInputLayer()
        result = layer.process("drawing.pdf")

        if result.is_accepted:
            engine_input = result.to_engine_input()
            # feed to engine...
    """

    def __init__(self, scale_factor: float = 1.0):
        """
        Args:
            scale_factor: Convert page units to real-world feet
        """
        self.scale_factor = scale_factor

    def process(self, pdf_path: str) -> InputLayerResult:
        """
        Process PDF through complete input layer.

        Args:
            pdf_path: Path to PDF floor plan

        Returns:
            InputLayerResult with extracted data
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
                parser_name="PDFInputLayer",
            )
            validate_file_size(
                safe_path,
                max_size_bytes=_MAX_FILE_SIZE_BYTES,
                parser_name="PDFInputLayer",
            )
        except UnsafePathError as e:
            raise ValueError(str(e)) from e

        result = InputLayerResult(
            source_pdf=pdf_path,
            confidence_result=None
        )

        # Step 1: Check confidence gate FIRST
        try:
            confidence = ParserConfidence(str(safe_path)).evaluate()
            result.confidence_result = confidence

            if confidence.gate == GateDecision.REJECT:
                result.errors.append("Drawing REJECTED by confidence gate")
                logger.warning("REJECTED: %s", confidence.message)
                return result

            if confidence.gate == GateDecision.CAUTION:
                result.warnings.append("Drawing marked CAUTION - manual review recommended")

        except Exception as e:
            result.errors.append(f"Confidence check failed: {e}")
            return result

        # Step 2: Extract actual data
        try:
            self._extract_data(str(safe_path), result)
        except Exception as e:
            import traceback
            full_tb = traceback.format_exc()
            result.errors.append(f"Data extraction failed: {e}")
            result.errors.append(f"Traceback: {full_tb}")
            logger.error("Extraction error: %s\n%s", e, full_tb)

        return result

    def _extract_data(self, pdf_path: str, result: InputLayerResult):
        """Extract devices, rooms, metadata from PDF."""
        # P0.3 FIX: dual-import — try repo shim first, then pymupdf directly.
        try:
            import _fitz_compat as fitz  # PyMuPDF (dev mode)
        except ImportError:
            import pymupdf as fitz  # type: ignore[no-redef]  (installed-package mode)

        doc = fitz.open(pdf_path)

        for page_num, page in enumerate(doc, 1):
            # Extract metadata from first page only
            if page_num == 1:
                result.metadata = self._extract_metadata(page)

            # Extract devices from this page
            devices = self._extract_devices(page, page_num)
            result.devices.extend(devices)

            # Extract rooms from this page
            rooms = self._extract_rooms(page, page_num)
            result.rooms.extend(rooms)

        doc.close()

    def _extract_metadata(self, page) -> DrawingMetadata:
        """Extract drawing metadata from text."""
        text = page.get_text().lower()

        metadata = DrawingMetadata()

        # Building name (look for project/building)
        match = re.search(r'(?:project|building)[:\s]*([^\n]+)', text)
        if match:
            metadata.building_name = match.group(1).strip()[:50]

        # Floor level
        floor_match = re.search(r'(?:floor|level)[:\s]*(ground|first|second|third|1st|2nd|3rd|\d+)', text)
        if floor_match:
            metadata.floor_level = floor_match.group(1).strip()

        # Scale
        scale_match = re.search(r'scale[:\s]*(\d+[:/]\d+|1/8"|1/4"|3/32")', text)
        if scale_match:
            metadata.drawing_scale = scale_match.group(1).strip()

        # Date
        date_match = re.search(r'(?:date|drawn)[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', text)
        if date_match:
            metadata.date = date_match.group(1).strip()

        # Designer
        designer_match = re.search(r'(?:designer|drawn by|prepared by)[:\s]*([^\n]+)', text)
        if designer_match:
            metadata.designer = designer_match.group(1).strip()[:50]

        # Revision
        rev_match = re.search(r'rev(?:ision)?[:\s]*([A-Z0-9]+)', text)
        if rev_match:
            metadata.revision = rev_match.group(1).strip()

        # North arrow check
        metadata.north_arrow = 'north' in text and 'arrow' in text

        return metadata

    def _extract_devices(self, page, page_num: int) -> List[ExtractedDevice]:
        """Extract fire alarm devices from page."""
        devices = []
        text = page.get_text().lower()

        # Get page dimensions for coordinate conversion
        page_rect = page.rect
        page_width = page_rect.width
        page_height = page_rect.height

        # Find each device type in text
        for symbol_pattern, device_type in NFPA_170_SYMBOLS.items():
            # Find all occurrences
            for match in re.finditer(re.escape(symbol_pattern), text):
                # Try to extract coordinates from nearby text
                x, y = self._extract_coordinates_near(text, match.start(), page_width, page_height)

                # Try to extract room from nearby text
                room = self._extract_room_near(text, match.start())

                # Calculate confidence based on position
                confidence = 0.7 if (x, y) != (0, 0) else 0.5

                devices.append(ExtractedDevice(
                    device_type=device_type,
                    x=x,
                    y=y,
                    page=page_num,
                    room=room,
                    confidence=confidence
                ))

        return self._deduplicate_devices(devices)

    def _extract_coordinates_near(self, text: str, position: int,
                              page_width: float, page_height: float) -> Tuple[float, float]:
        """Try to extract coordinates near match position."""
        # Look at text window around match
        window = text[max(0, position-30):position+30]

        # Try coordinates pattern (e.g., "12.5, 8.3" or "X=12.5 Y=8.3")
        coord_match = re.search(r'(\d+\.?\d*)[,\s]+(\d+\.?\d*)', window)
        if coord_match:
            try:
                x_raw = coord_match.group(1)
                y_raw = coord_match.group(2)
                # Ensure these are actually numeric, not sequences
                if not x_raw.replace('.', '').isdigit() or not y_raw.replace('.', '').isdigit():
                    return (0.0, 0.0)
                x = float(x_raw)
                y = float(y_raw)
                # Convert from page coords to real-world
                return (x * float(self.scale_factor), y * float(self.scale_factor))
            except (ValueError, TypeError):
                pass

        return (0.0, 0.0)

    def _extract_room_near(self, text: str, position: int) -> Optional[str]:
        """Extract room number near match position."""
        window = text[max(0, position-50):position+50]

        # Room patterns
        room_patterns = [
            r'(?:room|r\.?|#)\s*(\d+[A-Za-z]?)',
            r'(?:rm|r)[\s.-]*(\d+)',
            r'\b(\d+[A-Za-z]?)\s*$',
        ]

        for pattern in room_patterns:
            match = re.search(pattern, window, re.IGNORECASE)
            if match:
                return match.group(1).upper()

        return None

    def _extract_rooms(self, page, page_num: int) -> List[RoomBoundary]:
        """Extract room boundaries from page."""
        rooms = []
        text = page.get_text()
        text_lower = text.lower()

        # Get page dimensions

        # Known room names to look for
        KNOWN_ROOM_NAMES = [
            'corridor', 'lobby', 'office', 'kitchen', 'meeting',
            'bathroom', 'bedroom', 'warehouse', 'storage', 'server',
            'atrium'
        ]

        # First: try explicit "Room X" patterns
        room_matches = re.finditer(
            r'room\s*([A-Z]?\d+[A-Za-z]?)',
            text_lower,
            re.IGNORECASE
        )

        for match in room_matches:
            room_name = match.group(1).upper()
            area = self._extract_room_area(text_lower, match.start())
            ceiling = self._extract_ceiling_height(text_lower, match.start())

            # Get position safely
            try:
                bbox = page.get_text("bbox", match.span())
                if bbox and isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
                    try:
                        center_x = (float(bbox[0]) + float(bbox[2])) / 2.0
                        center_y = (float(bbox[1]) + float(bbox[3])) / 2.0
                    except (TypeError, ValueError):
                        center_x, center_y = 100.0, 100.0
                else:
                    center_x, center_y = 100.0, 100.0
            except Exception:
                center_x, center_y = 100.0, 100.0

            rooms.append(RoomBoundary(
                name=room_name,
                area_sqft=area or 100.0,
                center_x=center_x,
                center_y=center_y,
                ceiling_height=ceiling
            ))

        # Second: find known room names in text (Corridor, Lobby, etc)
        for room_keyword in KNOWN_ROOM_NAMES:
            pattern = re.compile(rf'\b{re.escape(room_keyword)}\b', re.IGNORECASE)
            for match in pattern.finditer(text_lower):
                room_name = match.group(0).title()
                # Skip if already have this room
                if any(r.name.lower() == room_name.lower() for r in rooms):
                    continue

                area = self._extract_room_area(text_lower, match.start())
                ceiling = self._extract_ceiling_height(text_lower, match.start())

                try:
                    bbox = page.get_text("bbox", match.span())
                    if bbox and isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
                        try:
                            center_x = (float(bbox[0]) + float(bbox[2])) / 2.0
                            center_y = (float(bbox[1]) + float(bbox[3])) / 2.0
                        except (TypeError, ValueError):
                            center_x, center_y = 100.0, 100.0
                    else:
                        center_x, center_y = 100.0, 100.0
                except Exception:
                    center_x, center_y = 100.0, 100.0

                rooms.append(RoomBoundary(
                    name=room_name,
                    area_sqft=area or 25.0,
                    center_x=center_x,
                    center_y=center_y,
                    ceiling_height=ceiling
                ))

        return rooms

    def _extract_room_area(self, text: str, position: int) -> Optional[float]:
        """Extract room area near position - ONLY look AFTER the room name."""
        # IMPORTANT: Only look AFTER position, not before (we need the area of THIS room)
        window = text[position:position+200]

        # Area patterns: sqft
        area_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:sq\.?\s*ft\.?|sf|sqft)', window)
        if area_match:
            try:
                return float(area_match.group(1))
            except ValueError:
                pass

        # Area patterns: m² (convert to sqft)
        area_match2 = re.search(r'(\d+(?:\.\d+)?)\s*(?:m2|m\.?²|sq\.?\s*m|square\s*m)', window)
        if area_match2:
            try:
                area_val = float(area_match2.group(1))
                # Convert m² to sqft
                return area_val * 10.764
            except ValueError:
                pass

        return None

    def _extract_ceiling_height(self, text: str, position: int) -> float:
        """Extract ceiling height from nearby text."""
        window = text[max(0, position-200):position+200]

        # Height patterns
        height_patterns = [
            r'ceiling[:\s]*(\d+(?:\.\d+)?)\s*(?:ft|feet|\')',
            r'(\d+(?:\.\d+)?)\s*ft\s+ceiling',
            r'height[:\s]*(\d+(?:\.\d+)?)\s*(?:ft|feet|\')',
        ]

        for pattern in height_patterns:
            match = re.search(pattern, window, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    pass

        return 9.0  # Default

    def _deduplicate_devices(self, devices: List[ExtractedDevice]) -> List[ExtractedDevice]:
        """Remove duplicate devices."""
        seen = {}
        unique = []

        for d in devices:
            key = (d.device_type.value, d.room, d.page)
            if key not in seen:
                seen[key] = d
                unique.append(d)

        return unique


# ═══════════════════════════════════════════════════════
# CONVENIENCE FUNCTION
# ═══════════════════════════════════════════════════════

def process_drawing(pdf_path: str) -> InputLayerResult:
    """
    Process a single drawing through the input layer.

    Args:
        pdf_path: Path to PDF floor plan

    Returns:
        InputLayerResult with extracted data
    """
    layer = PDFInputLayer()
    return layer.process(pdf_path)


def quick_accept_check(pdf_path: str) -> Tuple[bool, str]:
    """
    Quick check if drawing passes confidence gate.

    Returns:
        (accepted: bool, message: str)
    """
    try:
        confidence = ParserConfidence(pdf_path).evaluate()
        return (
            confidence.gate != GateDecision.REJECT,
            confidence.message
        )
    except Exception as e:
        return False, f"Error: {e}"
