"""
backend/routers/dwg.py — DWG/DXF file parsing endpoint.

Provides a single endpoint for uploading a DWG or DXF file and
receiving structured parsing results (room count, errors, etc.).

SAFETY:
  - Input path validation is delegated to parsers._path_security
    via DWGParser.parse(). The temp file is cleaned up after every
    request.
  - Auth gate: requires Permission.FILE_UPLOAD (added in rbac.py).
    The previous version was publicly callable — anonymous attackers
    could trigger CPU-heavy DWG parsing as a DoS vector.
  - Magic-byte sniffing: rejects files whose content does not match
    the declared extension (e.g. an .exe renamed to .dwg).
  - Chunked write: streams the upload directly to the temp file
    instead of buffering in memory (v1 doubled RAM usage).

v2 (2026-06-18):
  - Added `Depends(require_permission(Permission.FILE_UPLOAD))`.
  - Replaced `chunks = []; chunks.append(...); b''.join(chunks)`
    with streaming `out.write(chunk)` per chunk.
  - Added `_detect_real_format()` magic-byte sniffing.
  - Explicit `os.chmod(temp_path, 0o600)` for defense-in-depth.
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from backend.auth import require_permission
from backend.rbac import Permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/parse-dwg", tags=["dwg"])

_DWG_ALLOWED_EXTENSIONS = frozenset({".dwg", ".dxf"})

# C-5 FIX: Maximum upload size (100 MB) to prevent OOM attacks.
_MAX_DWG_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB
_CHUNK_SIZE = 1024 * 1024  # 1 MB per read

# DWG files start with "AC10" or "AC18" etc. (AutoCAD version code).
# We check only the first 2 bytes ("AC") for resilience to version drift.
_DWG_MAGIC_PREFIX = b"AC"

# DXF files are ASCII text starting with "0\nSECTION\n" (or "  0\nSECTION\n"
# with leading spaces). We check for the literal "SECTION" in the first
# 64 bytes — strict enough to reject binaries, lenient enough to accept
# real DXF exports from AutoCAD / LibreCAD / ezdxf.
_DXF_MAGIC_SUBSTRING = b"SECTION"
_DXF_SNIFF_LEN = 64


def _detect_real_format(first_bytes: bytes, declared_ext: str) -> bool:
    """Return True if the file's magic bytes match its declared extension.

    This is defense-in-depth against renamed executables or malicious
    payloads. Even if an attacker bypasses the extension check, the
    parser will receive a file whose content matches expectations.
    """
    if not first_bytes:
        return False
    if declared_ext == ".dwg":
        return first_bytes[:2] == _DWG_MAGIC_PREFIX
    if declared_ext == ".dxf":
        # DXF is ASCII; the SECTION keyword must appear near the top.
        head = first_bytes[:_DXF_SNIFF_LEN]
        return _DXF_MAGIC_SUBSTRING in head
    return False


@router.post("")
async def parse_dwg(
    file: UploadFile = File(...),  # noqa: B008  (FastAPI requires callable default)
    _role=Depends(require_permission(Permission.FILE_UPLOAD)),
):
    """Upload a DWG or DXF file for parsing.

    Returns structured parsing results including room count, conversion
    time, and any errors/warnings. On validation failure, returns a
    400-level error with details.

    Requires Permission.FILE_UPLOAD (ENGINEER or ADMIN role).
    """
    # ── Validate file extension ─────────────────────────────────────────
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in _DWG_ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file extension '{ext}'. Allowed: "
                f"{', '.join(sorted(_DWG_ALLOWED_EXTENSIONS))}"
            ),
        )

    # ── Save upload to a temp file with size limit ──────────────────────
    temp_path: Optional[str] = None
    try:
        # mkstemp already creates the file with 0600 on POSIX; the
        # explicit chmod below is for Windows + defense-in-depth.
        fd, temp_path = tempfile.mkstemp(suffix=ext, prefix="fireai_dwg_upload_")
        os.close(fd)
        try:
            os.chmod(temp_path, 0o600)
        except OSError:
            # chmod can fail on some filesystems (e.g. FAT32 in WSL).
            # Non-fatal — mkstemp already restricted permissions on POSIX.
            pass

        # Stream upload chunks directly to disk. The previous version
        # accumulated chunks in a list, then joined and wrote — doubling
        # RAM usage for the file size. For a 100MB upload that was 200MB
        # of RAM per request; now it is ~1MB regardless of file size.
        file_size = 0
        first_chunk: Optional[bytes] = None
        with open(temp_path, "wb") as out:
            while True:
                chunk = await file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                if first_chunk is None:
                    first_chunk = chunk
                file_size += len(chunk)
                if file_size > _MAX_DWG_SIZE_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            f"File too large (max {_MAX_DWG_SIZE_BYTES // (1024*1024)} MB). "
                            "Upload a smaller file or split the drawing."
                        ),
                    )
                out.write(chunk)

        # ── Validate non-empty file ─────────────────────────────────────
        if file_size == 0:
            raise HTTPException(
                status_code=422,
                detail={"success": False, "error": "Empty file uploaded"},
            )

        # ── Magic-byte sniffing ─────────────────────────────────────────
        # Reject files whose content does not match the declared extension.
        # This catches renamed executables, malicious payloads, and
        # accidental mis-labeled uploads.
        if not _detect_real_format(first_chunk or b"", ext):
            logger.warning(
                "DWG upload rejected: magic bytes do not match extension %s "
                "(first bytes: %r)",
                ext,
                (first_chunk or b"")[:16],
            )
            raise HTTPException(
                status_code=400,
                detail=(
                    f"File content does not match '{ext}' format. The file "
                    "may be corrupted, mis-labeled, or its extension was "
                    "renamed. Refusing to parse untrusted content."
                ),
            )

        # ── Parse via DWGParser ─────────────────────────────────────────
        try:
            from parsers.dwg_parser import DWGParser
        except ImportError as import_err:
            raise HTTPException(
                status_code=503,
                detail={
                    "success": False,
                    "error": f"DWG parser module unavailable: {import_err}",
                    "hint": "Ensure all parser dependencies are installed (ezdxf, pymupdf).",
                },
            )

        parser = DWGParser()
        result = parser.parse(temp_path)

        # ── Map result to HTTP response ─────────────────────────────────
        if not result.success:
            detail = {
                "success": False,
                "source": file.filename,
                "errors": result.errors,
                "warnings": result.warnings,
                "room_count": result.room_count,
                "conversion_time_s": result.conversion_time_s,
            }
            if result.errors and any("SECURITY" in e for e in result.errors):
                status_code = 400
            elif result.errors and any("not found" in e for e in result.errors):
                status_code = 404
            else:
                status_code = 422
            return JSONResponse(status_code=status_code, content=detail)

        return {
            "success": True,
            "source": file.filename,
            "room_count": result.room_count,
            "conversion_time_s": result.conversion_time_s,
            "errors": result.errors,
            "warnings": result.warnings,
        }

    except HTTPException:
        # Re-raise HTTPExceptions (400, 422, 503) — don't convert to 500.
        raise
    except Exception as exc:
        logger.error(
            "DWG parse request failed: %s: %s", type(exc).__name__, exc,
            exc_info=True,
        )
        # FIX: never leak internal exception text to the client. The
        # previous version returned the exception type, which is fine,
        # but we keep it that way and explicitly avoid `str(exc)`.
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": f"Internal error: {type(exc).__name__}",
            },
        )
    finally:
        # ── Clean up temp file ─────────────────────────────────────────
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except OSError as exc:
                logger.debug("Temp file cleanup failed: %s", exc)
