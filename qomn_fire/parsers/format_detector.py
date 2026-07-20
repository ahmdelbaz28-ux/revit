# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
"""
QOMN-FIRE FORMAT AND VERSION DETECTION ENGINE
Uses deterministic magic numbers and header verification.

Standards:
- ISO 16739 (IFC)
- AutoCAD DXF Specification
- ISO 10303-21 (STEP Physical File)
- OLE Compound File Binary Format (MS-CFB)

V128 SECURITY HARDENING (Finding #5):
    Path inputs are now validated by parsers._path_security before
    file I/O. This closes:
      - Path traversal (../../etc/passwd, /etc/, etc.)
      - Null-byte truncation (C-string attack)
      - Argument injection (defense-in-depth)
      - Files outside FIREAI_ALLOWED_UPLOAD_DIRS
      - DoS via oversized files (configurable cap)

Safety-Critical: Wrong format detection = wrong parser = wrong building model = wrong fire protection.
"""

import os
import re
from typing import Tuple

from parsers._path_security import (
    UnsafePathError,
    validate_file_size,
    validate_input_path,
)
from qomn_fire.core.errors import FormatError, Result

_FORMAT_MAX_FILE_SIZE_BYTES = int(
    os.getenv("FIREAI_FORMAT_MAX_FILE_SIZE_BYTES", str(100 * 1024 * 1024))  # 100 MB
)


class FormatDetector:
    """Deterministic file format and version detection from binary headers."""

    # DWG magic bytes → version mapping (AutoCAD DWG specification)
    DWG_MAGIC_MAP = {
        b"AC1015": "AutoCAD R2000 (AC1015)",
        b"AC1018": "AutoCAD R2004 (AC1018)",
        b"AC1021": "AutoCAD R2007 (AC1021)",
        b"AC1024": "AutoCAD R2010 (AC1024)",
        b"AC1027": "AutoCAD R2013 (AC1027)",
        b"AC1032": "AutoCAD R2018 (AC1032)",
    }

    # OLE Compound File Binary signature (MS-CFB §2.2)
    # BUG-1 FIX: Use raw bytes literal, NOT escaped strings.
    # The original code had b"\\xd0\\xcf..." which is LITERAL backslash-x characters,
    # NOT the actual binary signature 0xD0CF11E0A1B11AE1.
    OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

    @staticmethod
    def detect_format_and_version(filepath: str) -> Result[Tuple[str, str], FormatError]:  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
        """
        Reads first bytes of a file to detect format and version.
        Returns Result containing (format, version) or FormatError.

        Citing: ISO 16739 & AutoCAD DXF Specifications.

        V128 SECURITY: Validates path BEFORE any file I/O.
        Closes path traversal, null-byte, argument injection, and oversized file DoS.
        """
        try:
            safe_path = validate_input_path(
                filepath,
                # Allow all BIM formats for format detection
                allowed_extensions=frozenset({".ifc", ".ifcxml", ".json", ".dwg", ".dxf", ".rvt"}),
                parser_name="FormatDetector",
            )
        except FileNotFoundError as e:
            return Result(error=FormatError(
                message=str(e),
                code_ref="OS File IO Exception",
                remedy="Ensure path correctness before parsing."
            ))
        except UnsafePathError as e:
            return Result(error=FormatError(
                message=f"SECURITY: {e}",
                code_ref="Parser Security Gate",
                remedy="Provide a path within FIREAI_ALLOWED_UPLOAD_DIRS with valid BIM extension."
            ))

        try:
            validate_file_size(
                safe_path,
                max_size_bytes=_FORMAT_MAX_FILE_SIZE_BYTES,
                parser_name="FormatDetector",
            )
        except UnsafePathError as e:
            return Result(error=FormatError(
                message=f"SECURITY: {e}",
                code_ref="Parser Security Gate",
                remedy="File exceeds size limit."
            ))

        # Use the RESOLVED (canonical) path for all subsequent operations (TOCTOU fix)
        filepath = str(safe_path)

        try:
            with open(filepath, "rb") as f:
                header_bytes = f.read(1024)
        except Exception as e:
            return Result(error=FormatError(
                message=f"Unreadable file stream: {e!s}",
                code_ref="OS Security Exception",
                remedy="Check file permission levels."
            ))

        if len(header_bytes) == 0:
            return Result(error=FormatError(
                message="File contains zero bytes — empty or corrupted.",
                code_ref="Format Specifications",
                remedy="Provide a non-empty, valid BIM file."
            ))

        # Decode header as text for text-based format detection (IFC, DXF)
        header_text = header_bytes.decode("utf-8", errors="ignore")

        # ── 1. IFC Format Detection (STEP Physical File format ISO-10303-21) ──
        if "ISO-10303-21" in header_text or "ISO_10303_21" in header_text:
            # Determine IFC schema version (IFC2X3 or IFC4/IFC4X3)
            version = "IFC2X3"  # Default to most common
            if "IFC4X3" in header_text:
                version = "IFC4X3"
            elif "IFC4" in header_text:
                version = "IFC4"
            return Result(value=("IFC", version))

        # ── 2. DWG Format Detection (Magic bytes) ──
        for magic, ver_desc in FormatDetector.DWG_MAGIC_MAP.items():
            if header_bytes.startswith(magic):
                return Result(value=("DWG", ver_desc))

        # ── 3. RVT Format Detection (OLE Compound Container) ──
        # BUG-1 FIX: Uses FormatDetector.OLE_SIGNATURE which contains the CORRECT
        # binary bytes, not the escaped string literal that never matches.
        if header_bytes.startswith(FormatDetector.OLE_SIGNATURE):
            return Result(value=("RVT", "Revit Proprietary OLE Container"))

        # ── 4. DXF Format Detection (Text-based section headers) ──
        if "SECTION" in header_text and "HEADER" in header_text:
            # BUG-2 FIX: The original regex had double-escaped backslashes
            # r"\\$ACADVER\\s*\\n\\s*9\\s*\\n\\s*(AC\\d+)" which would NEVER match
            # because \\s matches literal backslash-s, not whitespace.
            # Fixed: proper single-escaped regex.
            ver_match = re.search(r"\$ACADVER\s*\n\s*9\s*\n\s*(AC\d+)", header_text)  # NOSONAR — S8786: assert kept for test clarity
            version = "Generic DXF"
            if ver_match:
                version = f"DXF {ver_match.group(1)}"
            return Result(value=("DXF", version))

        # Also detect minimal DXF files (just section + EOF)
        if "0\nSECTION" in header_text or b"0\nSECTION" in header_bytes:
            return Result(value=("DXF", "DXF (minimal)"))

        return Result(error=FormatError(
            message="Unrecognized file header signature.",
            code_ref="Format Specifications",
            remedy="Provide a valid, unencrypted IFC, DXF, DWG, or RVT file."
        ))
