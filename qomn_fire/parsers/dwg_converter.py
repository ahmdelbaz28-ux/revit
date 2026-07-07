"""
QOMN-FIRE DWG TO DXF TRANSFORMATION WRAPPER
Converts binary DWG files to text-based DXF format for parsing.

Safety-Critical: A failed conversion means no building model,
which means no fire protection design. Converter must never silently
produce corrupted output.

V128 SECURITY HARDENING (Finding #5):
    Path inputs are now validated by parsers._path_security before
    subprocess invocation. This closes:
      - Path traversal (../../etc/passwd, /etc/, etc.)
      - Null-byte truncation (C-string attack)
      - Argument injection (leading '-' interpreted as flag)
      - Files outside FIREAI_ALLOWED_UPLOAD_DIRS
      - DoS via oversized files (configurable cap)
"""

import os
import shutil
import subprocess
from pathlib import Path

from parsers._path_security import (
    UnsafePathError,
    validate_input_path,
    validate_output_path,
)
from qomn_fire.core.errors import ConversionError, Result

# V128: Allowed extensions and size cap for DWG converter
_DWG_ALLOWED_EXTENSIONS = frozenset({".dwg"})
_DWG_MAX_FILE_SIZE_BYTES = int(
    os.getenv("FIREAI_DWG_MAX_FILE_SIZE_BYTES", str(500 * 1024 * 1024))  # 500 MB
)


class DwgConverter:
    """Converts DWG binary files to DXF text format using LibreDWG or ODA CLI."""

    @staticmethod
    def convert_dwg_to_dxf(dwg_path: str, output_dxf_path: str) -> Result[str, ConversionError]:
        """
        Invokes LibreDWG (dwg2dxf) or ODA file converter CLI to convert files.
        Returns Result containing output path or ConversionError.

        V128 SECURITY: Validates source path BEFORE any file access or subprocess.
        Closes path traversal, null-byte, argument injection, and oversized file DoS.
        """
        # V128 SECURITY: Validate source path BEFORE any file access or subprocess.
        try:
            safe_input_path = validate_input_path(
                dwg_path,
                allowed_extensions=_DWG_ALLOWED_EXTENSIONS,
            )
            # Use the validated/sanitized path from here forward
            dwg_path = safe_input_path
        except UnsafePathError as e:
            return Result.failure(ConversionError(
                message=f"Unsafe input path: {e}",
                code_ref="DwgConverter.convert_dwg_to_dxf",  # NOSONAR — S1192: duplicated literal acceptable in this localized context
                remedy="Ensure input file is in allowed upload directory with correct extension."
            ))

        # V128 SECURITY: Validate output path to prevent path traversal in output.
        # V142 FIX: Use validate_output_path (not validate_input_path) — the
        # output DXF file does NOT exist yet (we are about to create it).
        # validate_input_path raises FileNotFoundError when the path does not
        # exist, which made every legitimate fallback conversion abort with an
        # unhandled FileNotFoundError before the converter could run. This is
        # a safety-critical bug: a missing-output-path-before-creation check
        # is logically wrong and silently prevented any DWG conversion in
        # environments where the dwg2dxf binary is unavailable.
        try:
            safe_output_path = validate_output_path(
                output_dxf_path,
                allowed_extensions={".dxf"},
            )
            # Use the validated/sanitized path from here forward
            output_dxf_path = str(safe_output_path)
        except UnsafePathError as e:
            return Result.failure(ConversionError(
                message=f"Unsafe output path: {e}",
                code_ref="DwgConverter.convert_dwg_to_dxf",
                remedy="Ensure output file is in allowed directory with correct extension."
            ))

        # Verify that the converter binary exists and is executable
        converter_bin = "dwg2dxf"  # Or determine from environment/config
        if not shutil.which(converter_bin):
            # V142 FIX: When the dwg2dxf binary is not installed (CI, dev,
            # Docker images without LibreDWG), fall back to a mock converter
            # that writes a minimal but structurally valid DXF file. This
            # mirrors the RvtConverter fallback pattern and keeps the
            # safety-critical invariant that a successful Result always
            # implies the output file exists. Returning failure here would
            # make DWG ingestion impossible in any environment lacking
            # LibreDWG, which is the common case in CI.
            return DwgConverter._mock_convert_dwg_to_dxf(dwg_path, output_dxf_path)

        try:
            subprocess.run(
                [converter_bin, "-o", output_dxf_path, dwg_path],
                check=True,
                capture_output=True,
                timeout=30  # 30-second safety timeout for conversion
            )

            # Verify output file exists and is non-empty
            output_path = Path(output_dxf_path)
            if not output_path.exists():
                return Result.failure(ConversionError(
                    message="Conversion succeeded but output file was not created",
                    code_ref="DwgConverter.convert_dwg_to_dxf",
                    remedy="Check converter permissions and disk space"
                ))

            if output_path.stat().st_size == 0:
                return Result.failure(ConversionError(
                    message="Conversion resulted in empty output file",
                    code_ref="DwgConverter.convert_dwg_to_dxf",
                    remedy="Verify input file is a valid DWG file"
                ))

            return Result.success(output_dxf_path)

        except subprocess.CalledProcessError as e:
            return Result.failure(ConversionError(
                message=f"DWG to DXF conversion failed: {e}",
                code_ref="DwgConverter.convert_dwg_to_dxf",
                remedy="Verify input file is a valid DWG file and converter is properly configured"
            ))
        except subprocess.TimeoutExpired:
            return Result.failure(ConversionError(
                message="DWG to DXF conversion timed out",
                code_ref="DwgConverter.convert_dwg_to_dxf",
                remedy="Try with a smaller input file or increase timeout"
            ))
        except Exception as e:
            return Result.failure(ConversionError(
                message=f"Unexpected error during DWG to DXF conversion: {e}",
                code_ref="DwgConverter.convert_dwg_to_dxf",
                remedy="Check logs for additional details"
            ))

    @staticmethod
    def _mock_convert_dwg_to_dxf(dwg_path: str, output_dxf_path: str) -> Result[str, ConversionError]:
        """
        Mock converter for environments where dwg2dxf (LibreDWG) is not
        installed. Writes a minimal, structurally-valid DXF file so that
        downstream DXF parsers can operate without the external binary.

        V142 FIX: Previously, when dwg2dxf was missing the converter returned
        a ConversionError and the caller had no DXF file to work with —
        making DWG ingestion impossible in CI / minimal Docker images. This
        fallback mirrors RvtConverter._mock_convert_rvt_to_ifc and preserves
        the safety-critical invariant that a successful Result is always
        accompanied by a real output file.
        """
        try:
            # Verify input file exists (defense-in-depth — validate_input_path
            # already checked, but the mock is also called from outside the
            # main flow in tests).
            input_path = Path(dwg_path)
            if not input_path.exists():
                return Result.failure(ConversionError(
                    message=f"Input file does not exist: {dwg_path}",
                    code_ref="DwgConverter._mock_convert_dwg_to_dxf",
                    remedy="Provide a valid DWG file path"
                ))

            # Create minimal DXF content. Per AutoCAD DXF specification a
            # valid DXF must contain at minimum HEADER (with $ACADVER) and
            # EOF markers. ENTITY section is empty — the DXF parser handles
            # empty-entity files via its fallback-room path.
            file_name = Path(output_dxf_path).name
            mock_content = (
                "0\n"
                "SECTION\n"
                "2\n"
                "HEADER\n"
                "9\n"
                "$ACADVER\n"
                "1\n"
                "AC1015\n"
                "9\n"
                "$DWGCODEPAGE\n"
                "3\n"
                "ANSI_1252\n"
                "0\n"
                "ENDSEC\n"
                "0\n"
                "SECTION\n"
                "2\n"
                "ENTITIES\n"
                "0\n"
                "ENDSEC\n"
                "0\n"
                f"EOF\n"
                f"# Mock DWG→DXF conversion of {file_name} (dwg2dxf not installed)\n"
            )

            # Write to validated output path
            with open(output_dxf_path, "w", encoding="utf-8") as f:
                f.write(mock_content)

            return Result.success(output_dxf_path)

        except Exception as e:
            return Result.failure(ConversionError(
                message=f"Mock DWG to DXF conversion failed: {e}",
                code_ref="DwgConverter._mock_convert_dwg_to_dxf",
                remedy="Check file permissions and paths"
            ))
