# File-level suppression removed per audit (V143 hardening).
# Per-line justified suppressions (e.g., '# noqa: S3776 ...') are preserved.
"""
excel_parser.py — FireAI Excel Room Data Parser
Parses room specifications from Excel files.

Expected columns:
    - name: Room name/number
    - width_m: Room width in meters
    - depth_m: Room depth in meters
    - height_m: Ceiling height in meters
    - detector_type: SMOKE, HEAT, COMBO (optional)
    - occupancy_type: office, residential, etc. (optional)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List

# top-level. This crashed the module on systems without pandas installed,
# even though path-security validation (the first stage of parse()) does NOT
# require pandas. Tests `test_parsers_security_v125.py::TestExcelParserSecurity`
# only exercise path validation, so they should pass without pandas.
#
# Root-cause fix: lazy-import pandas inside the methods that actually need it.
# To enable Excel parsing, install the parsing extras:
#   pip install -e ".[parsing]"
pd = None  # type: ignore[assignment]

logger = logging.getLogger("fireai.excel_parser")


def _lazy_import_pandas():
    """Lazily import pandas on first actual use."""
    global pd
    if pd is None:
        try:
            import pandas as _pd  # type: ignore
            pd = _pd
        except ImportError as e:
            raise ImportError(
                "pandas is required for Excel parsing. "
                "Install with: pip install pandas openpyxl  "
                f"(original error: {e})"
            ) from e
    return pd


# EXCEPTIONS
# ═══════════════════════════════════════════════════════

class ExcelParseError(Exception):
    """Raised when Excel parsing fails."""

    pass


# ═══════════════════════════════════════════════════════
# DATA CLASS
# ═══════════════════════════════════════════════════════

@dataclass
class ExcelRoom:
    """Room from Excel."""

    name: str
    width_m: float
    depth_m: float
    height_m: float
    detector_type: str = "SMOKE"
    occupancy_type: str = "office"

    @property
    def floor_area(self) -> float:
        return self.width_m * self.depth_m

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "width_m": self.width_m,
            "depth_m": self.depth_m,
            "height_m": self.height_m,
            "floor_area": self.floor_area,
            "detector_type": self.detector_type,
            "occupancy_type": self.occupancy_type,
        }


@dataclass
class ExcelParseResult:
    """Result of parsing Excel file."""

    source_file: str
    success: bool
    room_count: int = 0
    rooms: List[ExcelRoom] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════
# EXCEL PARSER
# ═══════════════════════════════════════════════════════

class ExcelParser:
    """
    Parses Excel room specifications into room objects.

    USAGE:
        parser = ExcelParser()
        result = parser.parse("project_rooms.xlsx")

        if result.success:
            print(f"Found {result.room_count} rooms")
    """

    REQUIRED_COLUMNS = ['name', 'width_m', 'depth_m', 'height_m']

    # Column aliases (flexible matching)
    COLUMN_ALIASES = {
        'name': ['name', 'room', 'room_name', 'room_number', 'number', 'room_id'],
        'width_m': ['width_m', 'width', 'width_meters', 'w'],
        'depth_m': ['depth_m', 'depth', 'depth_meters', 'd', 'length'],
        'height_m': ['height_m', 'height', 'height_meters', 'h', 'ceiling_height'],
        'detector_type': ['detector_type', 'detector', 'type', 'device_type'],
        'occupancy_type': ['occupancy_type', 'occupancy', 'use', 'usage', 'room_type'],
    }

    def __init__(self, min_area: float = 2.0):
        """
        Args:
        min_area: Minimum room area in m² (default 2.0)

        """
        self.min_area = min_area

    def parse(self, file_path: str) -> ExcelParseResult:
        """
        Parse Excel file to rooms.

        Args:
            file_path: Path to .xlsx or .xls file. MUST be under
                FIREAI_ALLOWED_UPLOAD_DIRS (V124 security hardening).

        Returns:
            ExcelParseResult with room list

        """
        from parsers._path_security import (
            UnsafePathError,
            validate_file_size,
            validate_input_path,
        )
        _ALLOWED_EXTENSIONS = frozenset({".xlsx", ".xls", ".csv"})
        _MAX_FILE_SIZE_BYTES = int(os.getenv("FIREAI_EXCEL_MAX_FILE_SIZE_BYTES", 25 * 1024 * 1024))  # 25 MB default
        try:
            safe_path = validate_input_path(
                file_path,
                allowed_extensions=_ALLOWED_EXTENSIONS,
                parser_name="ExcelParser",
            )
            validate_file_size(
                safe_path,
                max_size_bytes=_MAX_FILE_SIZE_BYTES,
                parser_name="ExcelParser",
            )
        except FileNotFoundError as e:
            return ExcelParseResult(source_file=file_path, success=False, errors=[str(e)])
        except UnsafePathError as e:
            return ExcelParseResult(source_file=file_path, success=False, errors=[f"SECURITY: {e}"])

        file_path = str(safe_path)
        result = ExcelParseResult(source_file=file_path, success=False)

        try:
            _lazy_import_pandas()
            # Read Excel
            df = pd.read_excel(str(safe_path), engine='openpyxl')

            if df.empty:
                result.errors.append("Excel file is empty")
                return result

            # Normalize columns
            df = self._normalize_columns(df)

            # Verify required columns
            missing = set(self.REQUIRED_COLUMNS) - set(df.columns)
            if missing:
                result.errors.append(f"Missing required columns: {missing}")
                return result

            # Parse rooms
            for idx, row in df.iterrows():
                try:
                    room = self._parse_row(row)
                    if room.floor_area >= self.min_area:
                        result.rooms.append(room)
                    else:
                        result.warnings.append(
                            f"Skipped {room.name}: area {room.floor_area:.1f}m² < {self.min_area}m²"
                        )
                except ValueError as e:
                    result.warnings.append(f"Row {idx+1}: {e}")

            result.room_count = len(result.rooms)
            result.success = result.room_count > 0

        except Exception as e:
            result.errors.append(f"Parse error: {type(e).__name__}: {e}")

        return result

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize column names to standard format."""
        df = df.copy()

        for standard, aliases in self.COLUMN_ALIASES.items():
            for alias in aliases:
                if alias in df.columns:
                    df.rename(columns={alias: standard}, inplace=True)
                    break

        return df

    def _parse_row(self, row: pd.Series) -> ExcelRoom:
        """Parse single row to ExcelRoom."""
        name = str(row['name']).strip()

        width = float(row['width_m'])
        depth = float(row['depth_m'])
        height = float(row['height_m'])

        if width <= 0 or depth <= 0 or height <= 0:
            raise ValueError(f"Invalid dimensions for {name}")

        detector_str = str(row.get('detector_type', 'SMOKE')).strip().upper()
        occupancy_str = str(row.get('occupancy_type', 'office')).strip().lower()

        return ExcelRoom(
            name=name,
            width_m=width,
            depth_m=depth,
            height_m=height,
            detector_type=detector_str,
            occupancy_type=occupancy_str,
        )


# ═══════════════════════════════════════════════════════
# CONVENIENCE FUNCTION
# ═══════════════════════════════════════════════════════

def parse_excel(file_path: str) -> ExcelParseResult:
    """Quick parse Excel file."""
    parser = ExcelParser()
    return parser.parse(file_path)
