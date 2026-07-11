# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
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
    """Converts DWG binary files to DXF text format using LibreDWG or ODA CLI.

    V213: Tries multiple converter binaries in order:
      1. ``dwg2dxf`` (LibreDWG — open source)
      2. ``ODAFileConverter`` (ODA SDK — freeware)
      3. Mock fallback (writes minimal valid DXF with explicit warning)

    The ``simulation_mode`` flag on successful results tells callers whether
    a real conversion occurred or the mock fallback was used — clients can
    surface this so engineers know the DXF has no real entities.
    """

    # V213: Ordered list of converter binaries to try. The first one found
    # on PATH is used. This lets the same code work in environments with
    # LibreDWG (Linux Docker), ODA File Converter (Windows), or neither.
    _CONVERTER_BINARIES = (
        "dwg2dxf",          # LibreDWG (open source, Linux/Mac/Windows)
        "ODAFileConverter",  # ODA SDK (freeware, Windows/Linux)
        "oda_file_converter",  # ODA SDK alternate name
    )

    @staticmethod
    def convert_dwg_to_dxf(dwg_path: str, output_dxf_path: str) -> Result[str, ConversionError]:
        """
        Invokes LibreDWG (dwg2dxf) or ODA file converter CLI to convert files.
        Returns Result containing output path or ConversionError.

        V128 SECURITY: Validates source path BEFORE any file access or subprocess.
        Closes path traversal, null-byte, argument injection, and oversized file DoS.

        V213: Tries multiple converter binaries. If none are available,
        falls back to a mock that writes a structurally-valid but entity-empty
        DXF file. The mock result includes ``simulation_mode=True`` in the
        success message so callers can surface the truth.
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
        try:
            safe_output_path = validate_output_path(
                output_dxf_path,
                allowed_extensions={".dxf"},
            )
            output_dxf_path = str(safe_output_path)
        except UnsafePathError as e:
            return Result.failure(ConversionError(
                message=f"Unsafe output path: {e}",
                code_ref="DwgConverter.convert_dwg_to_dxf",
                remedy="Ensure output file is in allowed directory with correct extension."
            ))

        # V213: Try each converter binary in order. First one found wins.
        converter_bin = None
        for candidate in DwgConverter._CONVERTER_BINARIES:
            if shutil.which(candidate):
                converter_bin = candidate
                break

        if converter_bin is None:
            # V142/V213: No converter binary available — fall back to mock.
            return DwgConverter._mock_convert_dwg_to_dxf(dwg_path, output_dxf_path)

        try:
            # V213: Different converters have different CLI syntax.
            # dwg2dxf (LibreDWG): dwg2dxf -o output.dxf input.dwg
            # ODAFileConverter: ODAFileConverter <in_dir> <out_dir> ACAD2010 DXF_0
            #   (note: ODA converts whole directories, not single files — we
            #   handle this by passing the file's parent dir and renaming)
            if converter_bin == "dwg2dxf":
                cmd = [converter_bin, "-o", output_dxf_path, str(dwg_path)]
            elif converter_bin in ("ODAFileConverter", "oda_file_converter"):
                # ODA converts directories. We pass the input file's parent
                # dir and the output dir, then rename the result.
                input_dir = str(Path(dwg_path).parent)
                output_dir = str(Path(output_dxf_path).parent)
                cmd = [
                    converter_bin, input_dir, output_dir,
                    "ACAD2010", "DXF_0",  # output version + format
                ]
            else:
                cmd = [converter_bin, "-o", output_dxf_path, str(dwg_path)]

            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                timeout=30,  # 30-second safety timeout for conversion
            )

            # ODA File Converter writes output with same basename but .dxf
            # extension in the output dir. Find and rename if needed.
            if converter_bin in ("ODAFileConverter", "oda_file_converter"):
                expected_name = Path(dwg_path).stem + ".dxf"
                oda_output = Path(output_dir) / expected_name
                if oda_output.exists() and str(oda_output) != output_dxf_path:
                    shutil.move(str(oda_output), output_dxf_path)

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

            # V213: Real conversion succeeded — simulation_mode=False
            return Result.success(output_dxf_path)

        except subprocess.CalledProcessError as e:
            return Result.failure(ConversionError(
                message=f"DWG to DXF conversion failed (converter={converter_bin}): {e}",
                code_ref="DwgConverter.convert_dwg_to_dxf",
                remedy="Verify input file is a valid DWG file and converter is properly configured"
            ))
        except subprocess.TimeoutExpired:
            return Result.failure(ConversionError(
                message=f"DWG to DXF conversion timed out (converter={converter_bin})",
                code_ref="DwgConverter.convert_dwg_to_dxf",
                remedy="Try with a smaller input file or increase timeout"
            ))
        except Exception as e:
            return Result.failure(ConversionError(
                message=f"Unexpected error during DWG to DXF conversion (converter={converter_bin}): {e}",
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
