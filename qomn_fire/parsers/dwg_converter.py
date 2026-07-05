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
                max_size_bytes=_DWG_MAX_FILE_SIZE_BYTES,
            )
            # Use the validated/sanitized path from here forward
            dwg_path = safe_input_path
        except UnsafePathError as e:
            return Result.failure(ConversionError(
                message=f"Unsafe input path: {e}",
                code_ref="DwgConverter.convert_dwg_to_dxf",
                remedy="Ensure input file is in allowed upload directory with correct extension."
            ))

        # V128 SECURITY: Validate output path to prevent path traversal in output
        try:
            safe_output_path = validate_input_path(
                output_dxf_path,
                allowed_extensions={".dxf"},
                max_size_bytes=None,  # Output size not limited at this stage
            )
            # Use the validated/sanitized path from here forward
            output_dxf_path = safe_output_path
        except UnsafePathError as e:
            return Result.failure(ConversionError(
                message=f"Unsafe output path: {e}",
                code_ref="DwgConverter.convert_dwg_to_dxf",
                remedy="Ensure output file is in allowed directory with correct extension."
            ))

        # Verify that the converter binary exists and is executable
        converter_bin = "dwg2dxf"  # Or determine from environment/config
        if not shutil.which(converter_bin):
            return Result.failure(ConversionError(
                message=f"Converter binary '{converter_bin}' not found in PATH",
                code_ref="DwgConverter.convert_dwg_to_dxf",
                remedy="Install LibreDWG tools (dwg2dxf command)"
            ))

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
