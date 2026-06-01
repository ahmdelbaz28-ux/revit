"""
QOMN-FIRE CRITICAL FILE VALIDATOR
Guarantees file safety, size limits, and checks for physical file corruption.

Safety-Critical: A corrupted BIM file produces wrong building geometry,
which produces wrong fire protection designs, which can kill people.

Standards: ISO 10303-21 §6 (STEP file structure), AutoCAD DXF Specification
"""

import os
import hashlib
from typing import Union

from qomn_fire.core.errors import Result, FileValidationError, CorruptionError
from qomn_fire.parsers.format_detector import FormatDetector


# 1 Gigabyte safety limit — files larger than this likely contain
# unreasonably complex geometry or are corrupted
MAX_FILE_SIZE_BYTES = 1024 * 1024 * 1024


class FileValidator:
    """Validates file existence, readability, size limits, and structural integrity."""

    @staticmethod
    def validate_file(filepath: str) -> Result[str, Union[FileValidationError, CorruptionError]]:
        """
        Validates file existence, readability, size limits, and returns file SHA-256 hash.
        Returns Result containing SHA-256 hex digest or error.
        """
        # ── Step 1: Existence check ──
        if not os.path.exists(filepath):
            return Result(error=FileValidationError(
                message=f"File not found on disk at: '{filepath}'",
                code_ref="OS IO API",
                remedy="Verify file directory path and name parameters."
            ))

        # ── Step 2: Readability check ──
        if not os.access(filepath, os.R_OK):
            return Result(error=FileValidationError(
                message=f"Permissions error: File not readable at: '{filepath}'",
                code_ref="OS File System",
                remedy="Grant read permissions to the running process."
            ))

        # ── Step 3: Zero-byte check ──
        file_size = os.path.getsize(filepath)
        if file_size == 0:
            return Result(error=FileValidationError(
                message="Target file contains zero bytes.",
                code_ref="BIM File Standard",
                remedy="Discard corrupted empty export file."
            ))

        # ── Step 4: Size limit check ──
        if file_size > MAX_FILE_SIZE_BYTES:
            return Result(error=FileValidationError(
                message=f"File exceeds absolute 1GB safety limit ({file_size / (1024*1024):.1f}MB).",
                code_ref="BIM File Standard",
                remedy="Partition the layout or crop irrelevant coordinates."
            ))

        # ── Step 5: Format detection (validates file is a known BIM format) ──
        format_res = FormatDetector.detect_format_and_version(filepath)
        if format_res.is_failure:
            return Result(error=CorruptionError(
                message="File headers do not match any known specifications.",
                code_ref="Format Detector",
                remedy="Open in native CAD tool and re-save."
            ))

        fmt, _ = format_res.unwrap()

        # ── Step 6: Structural corruption checks ──
        # BUG-6 FIX: Original code opened binary files with "r" (text mode),
        # which could cause decoding errors or wrong byte counts on binary files.
        # Now uses "rb" for binary reads consistently.

        if fmt == "IFC":
            # IFC must end with "END-ISO-10303-21;" per ISO 10303-21 §6
            try:
                with open(filepath, "rb") as bf:
                    bf.seek(max(0, file_size - 2000))
                    footer = bf.read().decode("utf-8", errors="ignore")
                if "END-ISO-10303-21;" not in footer:
                    return Result(error=CorruptionError(
                        message="IFC File is corrupted: Missing mandatory END-ISO-10303-21; footer line.",
                        code_ref="ISO 10303-21 §6",
                        remedy="Re-export the IFC file from Revit or ArchiCAD."
                    ))
            except Exception as e:
                return Result(error=CorruptionError(
                    message=f"IFC footer read failed: {str(e)}",
                    code_ref="OS IO Stream",
                    remedy="Verify file physical disk integrity."
                ))

        elif fmt == "DXF":
            # DXF must end with "EOF" per AutoCAD DXF Specification
            try:
                with open(filepath, "rb") as bf:
                    bf.seek(max(0, file_size - 500))
                    footer = bf.read().decode("utf-8", errors="ignore")
                if "EOF" not in footer:
                    return Result(error=CorruptionError(
                        message="DXF File is corrupted: Missing final EOF (End Of File) section marker.",
                        code_ref="AutoCAD DXF Specification",
                        remedy="Re-save drawing file using standard DWG/DXF exporter."
                    ))
            except Exception as e:
                return Result(error=CorruptionError(
                    message=f"DXF footer read failed: {str(e)}",
                    code_ref="OS IO Stream",
                    remedy="Re-save drawing on standard solid state memory."
                ))

        # ── Step 7: Cryptographic SHA-256 hash for traceability ──
        # This hash is used for audit trail and liability tracking.
        sha = hashlib.sha256()
        try:
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    sha.update(chunk)
            return Result(value=sha.hexdigest())
        except Exception as e:
            return Result(error=FileValidationError(
                message=f"Hashing sequence crashed: {str(e)}",
                code_ref="OS Cryptography Engine",
                remedy="Verify file physical disk integrity."
            ))
