"""
parsers/ddc_adapter.py — DataDrivenConstruction (DDC) Converter CLI Adapter

INTEGRATION: cad2data-Revit-IFC-DWG-DGN (https://github.com/datadrivenconstruction/cad2data-Revit-IFC-DWG-DGN)

PURPOSE:
    Bridge between FireAI's parser layer and the DDC CLI converters:
    - ddc-rvtconverter  → Revit .rvt → XLSX + DAE
    - ddc-dwgconverter  → AutoCAD .dwg → XLSX + DAE
    - ddc-ifcconverter  → IFC → XLSX + DAE
    - ddc-dgnconverter  → MicroStation .dgn → XLSX + DAE

ARCHITECTURE:
    FireAI Workflow → DDCAdapter.convert() → subprocess(ddc-*converter) → XLSX
    FireAI Workflow → DDCAdapter.to_rooms() → IFC/rooms list for device placement

LICENSING NOTE:
    DDC converter binaries are proprietary (DDC EULA + ODA Sustaining Member license).
    CLI execution is permitted under the EULA for integration purposes.
    Source code of converters is NOT available.

INSTALLATION (Linux):
    curl -sS https://pkg.datadrivenconstruction.io/setup.sh | sudo bash
    sudo apt install ddc-rvtconverter ddc-dwgconverter ddc-ifcconverter

FALLBACK:
    If DDC converters are not installed, each method raises DDCNotAvailableError.
    The caller must handle this and fall back to ezdxf/ifcopenshell or manual input.

SAFETY:
    DDC output is used as geometry INPUT to NFPA 72 calculations.
    It is NOT authoritative for compliance — all extracted data flows through
    the validation layer before reaching the device placement engine.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# DDC CLI binary names (Linux .deb installed to /usr/bin/)
_DDC_CONVERTERS: Dict[str, str] = {
    ".rvt": "ddc-rvtconverter",
    ".rfa": "ddc-rvtconverter",
    ".dwg": "ddc-dwgconverter",
    ".ifc": "ddc-ifcconverter",
    ".dgn": "ddc-dgnconverter",
}

# Windows .exe equivalents (fallback for Windows deployments)
_DDC_CONVERTERS_WIN: Dict[str, str] = {
    ".rvt": "RvtExporter.exe",
    ".rfa": "RvtExporter.exe",
    ".dwg": "DwgExporter.exe",
    ".ifc": "IfcExporter.exe",
    ".dgn": "DgnExporter.exe",
}


class DDCNotAvailableError(RuntimeError):
    """Raised when DDC CLI converter is not installed."""
    pass


@dataclass
class DDCConversionResult:
    """Result of a DDC converter run."""
    success: bool
    source_file: str
    xlsx_path: Optional[str] = None
    dae_path: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    rooms: List[Dict[str, Any]] = field(default_factory=list)
    elements: List[Dict[str, Any]] = field(default_factory=list)
    duration_s: float = 0.0


class DDCAdapter:
    """
    Adapter for DDC (DataDrivenConstruction) CLI converters.

    Converts proprietary BIM/CAD formats to open XLSX/DAE for FireAI analysis.

    THREAD SAFETY: Each convert() call uses a separate temp directory.
    SAFETY: Output is advisory geometry — validated before use in calculations.
    """

    def __init__(self, converter_dir: Optional[str] = None):
        """
        Initialize DDC adapter.

        Args:
            converter_dir: Optional path to DDC .exe directory (Windows).
                          On Linux, converters must be on $PATH via apt install.
        """
        self._converter_dir = converter_dir
        self._platform = "windows" if os.name == "nt" else "linux"

    def is_available(self, file_ext: str) -> bool:
        """Check if DDC converter is available for the given file extension."""
        ext = file_ext.lower()
        binary = self._get_binary(ext)
        if binary is None:
            return False
        try:
            result = subprocess.run(
                ["which", binary] if self._platform == "linux" else ["where", binary],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _get_binary(self, ext: str) -> Optional[str]:
        """Get the DDC binary name for a file extension."""
        if self._platform == "windows":
            binary = _DDC_CONVERTERS_WIN.get(ext)
            if binary and self._converter_dir:
                return str(Path(self._converter_dir) / binary)
            return binary
        return _DDC_CONVERTERS.get(ext)

    def convert(
        self,
        input_path: str,
        export_mode: str = "standard",
        output_dir: Optional[str] = None,
    ) -> DDCConversionResult:
        """
        Convert a CAD/BIM file using the appropriate DDC converter.

        Args:
            input_path: Path to .rvt, .dwg, .ifc, or .dgn file
            export_mode: DDC export mode (basic/standard/complete) for Revit
            output_dir: Output directory (defaults to temp dir)

        Returns:
            DDCConversionResult with paths to generated XLSX/DAE files

        Raises:
            DDCNotAvailableError: If DDC converter not installed
            FileNotFoundError: If input file doesn't exist
        """
        import time
        start = time.monotonic()

        input_path_obj = Path(input_path)
        if not input_path_obj.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        # SECURITY FIX: Resolve the path and verify it's within an allowed
        # directory. This prevents path traversal attacks where a malicious
        # input_path like "/etc/passwd" or "../../../etc/shadow" could be
        # passed to the subprocess. Only files within designated upload/data
        # directories are permitted.
        safe_path = input_path_obj.resolve()

        # Allowed base directories (configurable via env var)
        _allowed_bases_str = os.getenv(
            "FIREAI_ALLOWED_UPLOAD_DIRS",
            "/tmp,/var/tmp,/var/fireai/uploads",
        )
        _allowed_bases = [
            Path(d).resolve() for d in _allowed_bases_str.split(",") if d.strip()
        ]

        # Always allow temp directories (created by tempfile.mkdtemp)
        _temp_dir = Path(tempfile.gettempdir()).resolve()
        if _temp_dir not in _allowed_bases:
            _allowed_bases.append(_temp_dir)

        # Also allow the current working directory (for development)
        _cwd = Path.cwd().resolve()
        if _cwd not in _allowed_bases:
            _allowed_bases.append(_cwd)

        # Verify path is within an allowed directory
        _path_in_allowed_dir = False
        for base in _allowed_bases:
            try:
                safe_path.relative_to(base)
                _path_in_allowed_dir = True
                break
            except ValueError:
                continue

        if not _path_in_allowed_dir:
            raise ValueError(
                f"SECURITY: Input file path '{safe_path}' is outside allowed "
                f"directories. Path traversal detected. Allowed bases: "
                f"{[str(b) for b in _allowed_bases]}"
            )

        # SECURITY FIX: Verify the resolved path hasn't been tampered with
        # via symlinks pointing outside allowed directories.
        if safe_path.is_symlink():
            real_target = safe_path.readlink().resolve()
            _real_in_allowed = False
            for base in _allowed_bases:
                try:
                    real_target.relative_to(base)
                    _real_in_allowed = True
                    break
                except ValueError:
                    continue
            if not _real_in_allowed:
                raise ValueError(
                    f"SECURITY: Symlink target '{real_target}' is outside "
                    f"allowed directories. Symlink traversal detected."
                )

        ext = input_path_obj.suffix.lower()

        # SECURITY FIX: Validate file extension against allowed set BEFORE
        # any subprocess invocation. Prevents path traversal or unexpected
        # file types from reaching the converter binary.
        _ALLOWED_EXTENSIONS = frozenset(_DDC_CONVERTERS.keys())
        if ext not in _ALLOWED_EXTENSIONS:
            raise ValueError(
                f"File extension '{ext}' is not allowed. "
                f"Permitted extensions: {sorted(_ALLOWED_EXTENSIONS)}"
            )

        binary = self._get_binary(ext)
        if binary is None:
            raise DDCNotAvailableError(
                f"No DDC converter registered for extension '{ext}'. "
                f"Supported: {list(_DDC_CONVERTERS.keys())}"
            )

        if not self.is_available(ext):
            raise DDCNotAvailableError(
                f"DDC converter '{binary}' not found on PATH. "
                f"Install with: sudo apt install {_DDC_CONVERTERS.get(ext, binary)}"
            )

        # Use temp dir if no output specified
        _temp = None
        if output_dir is None:
            _temp = tempfile.mkdtemp(prefix="fireai_ddc_")
            output_dir = _temp

        try:
            cmd = [binary, str(safe_path)]
            if export_mode and ext in (".rvt", ".rfa"):
                # SECURITY FIX: Whitelist export_mode to prevent command
                # injection. Without validation, a malicious export_mode
                # could pass unexpected flags to the DDC converter binary.
                _ALLOWED_EXPORT_MODES = frozenset({"basic", "standard", "complete"})
                if export_mode not in _ALLOWED_EXPORT_MODES:
                    raise ValueError(
                        f"Invalid export_mode '{export_mode}'. "
                        f"Permitted values: {sorted(_ALLOWED_EXPORT_MODES)}"
                    )
                cmd.append(export_mode)

            logger.info(f"DDC convert: {' '.join(cmd)} → {output_dir}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=output_dir,
                timeout=300,  # 5 min max
            )

            duration = time.monotonic() - start

            if result.returncode != 0:
                return DDCConversionResult(
                    success=False,
                    source_file=str(input_path),
                    errors=[f"DDC converter failed (exit {result.returncode}): {result.stderr[:500]}"],
                    duration_s=duration,
                )

            # Find generated output files
            stem = input_path_obj.stem
            xlsx_path = Path(output_dir) / f"{stem}_rvt.xlsx"
            if not xlsx_path.exists():
                # DDC sometimes uses the full filename
                for f in Path(output_dir).glob("*.xlsx"):
                    xlsx_path = f
                    break

            dae_path = Path(output_dir) / f"{stem}.dae"
            if not dae_path.exists():
                dae_path = None  # type: ignore[assignment]

            conv_result = DDCConversionResult(
                success=True,
                source_file=str(input_path),
                xlsx_path=str(xlsx_path) if xlsx_path and xlsx_path.exists() else None,
                dae_path=str(dae_path) if dae_path else None,
                duration_s=duration,
            )

            # Parse XLSX for room/element data
            if conv_result.xlsx_path:
                conv_result.rooms = self._extract_rooms_from_xlsx(conv_result.xlsx_path)
                conv_result.elements = self._extract_elements_from_xlsx(conv_result.xlsx_path)

            logger.info(
                f"DDC convert OK: {input_path_obj.name} → "
                f"{len(conv_result.rooms)} rooms, {len(conv_result.elements)} elements "
                f"in {duration:.1f}s"
            )
            return conv_result

        except subprocess.TimeoutExpired:
            return DDCConversionResult(
                success=False,
                source_file=str(input_path),
                errors=["DDC converter timed out after 300s — file may be too large"],
                duration_s=300.0,
            )
        except Exception as e:
            logger.error(f"DDC convert error: {e}", exc_info=True)
            return DDCConversionResult(
                success=False,
                source_file=str(input_path),
                errors=[f"{type(e).__name__}: {e}"],
            )

    def _extract_rooms_from_xlsx(self, xlsx_path: str) -> List[Dict[str, Any]]:
        """
        Extract room/space data from DDC-generated XLSX.

        DDC XLSX columns include: Category, Type Name, Level, Area, Volume,
        Width, Height, Number, Name, and geometry parameters.
        """
        try:
            import openpyxl
        except ImportError:
            try:
                import xlrd  # type: ignore[import-not-found]
                return self._extract_rooms_xlrd(xlsx_path)
            except ImportError:
                logger.warning("openpyxl not installed — cannot parse DDC XLSX output")
                return []

        rooms = []
        try:
            wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
            ws = wb.active
            if ws is None:
                return []

            headers = []
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i == 0:
                    headers = [str(h).strip() if h else "" for h in row]
                    continue

                row_dict = dict(zip(headers, row))
                category = str(row_dict.get("Category", "")).lower()

                # Rooms are "Rooms" category in Revit, "IfcSpace" in IFC
                if "room" in category or "space" in category:
                    area = row_dict.get("Area", 0) or 0
                    # DDC exports in ft² for imperial projects — check unit
                    rooms.append({
                        "name": row_dict.get("Name", "") or row_dict.get("Number", ""),
                        "area_m2": float(area) if area else 0.0,
                        "level": str(row_dict.get("Level", "")) or "1",
                        "volume_m3": float(row_dict.get("Volume", 0) or 0),
                        "source": "ddc",
                        "raw": row_dict,
                    })

            wb.close()
        except Exception as e:
            logger.error(f"DDC XLSX room extraction failed: {e}", exc_info=True)

        return rooms

    def _extract_elements_from_xlsx(self, xlsx_path: str) -> List[Dict[str, Any]]:
        """Extract all BIM elements from DDC XLSX."""
        try:
            import openpyxl
        except ImportError:
            return []

        elements = []
        try:
            wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
            ws = wb.active
            if ws is None:
                return []

            headers = []
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i == 0:
                    headers = [str(h).strip() if h else "" for h in row]
                    continue
                row_dict = dict(zip(headers, row))
                elements.append(row_dict)

            wb.close()
        except Exception as e:
            logger.error(f"DDC XLSX element extraction failed: {e}", exc_info=True)

        return elements

    def _extract_rooms_xlrd(self, xlsx_path: str) -> List[Dict[str, Any]]:
        """Fallback room extraction using xlrd (for .xls files)."""
        import xlrd  # type: ignore[import-not-found]
        rooms = []
        try:
            wb = xlrd.open_workbook(xlsx_path)
            ws = wb.sheet_by_index(0)
            headers = [str(ws.cell_value(0, c)).strip() for c in range(ws.ncols)]
            for r in range(1, ws.nrows):
                row_dict = {headers[c]: ws.cell_value(r, c) for c in range(ws.ncols)}
                category = str(row_dict.get("Category", "")).lower()
                if "room" in category or "space" in category:
                    rooms.append({
                        "name": row_dict.get("Name", ""),
                        "area_m2": float(row_dict.get("Area", 0) or 0),
                        "level": str(row_dict.get("Level", "1")),
                        "source": "ddc",
                        "raw": row_dict,
                    })
        except Exception as e:
            logger.error(f"xlrd extraction failed: {e}", exc_info=True)
        return rooms


def get_ddc_adapter(converter_dir: Optional[str] = None) -> DDCAdapter:
    """Get a DDCAdapter instance (simple factory, no singleton needed)."""
    return DDCAdapter(converter_dir=converter_dir)
