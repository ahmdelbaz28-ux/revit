"""
backend/routers/dwg.py — DWG/DXF file parsing endpoint.

Provides a single endpoint for uploading a DWG or DXF file and
receiving structured parsing results (room count, errors, etc.).

SAFETY: Input path validation is delegated to parsers._path_security
via DWGParser.parse(). The temp file is cleaned up after every request.
"""

from __future__ import annotations

import logging
import os
import tempfile

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/parse-dwg", tags=["dwg"])

_DWG_ALLOWED_EXTENSIONS = frozenset({".dwg", ".dxf"})

# C-5 FIX: Maximum upload size (100 MB) to prevent OOM attacks.
# A safety-critical system must not be vulnerable to DoS via oversized uploads.
_MAX_DWG_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB


@router.post("")
async def parse_dwg(file: UploadFile = File(...)):  # noqa: B008
    """
    Upload a DWG or DXF file for parsing.

    Returns structured parsing results including room count, conversion
    time, and any errors/warnings. On validation failure, returns a
    400-level error with details.
    """
    # ── Validate file extension ─────────────────────────────────────────
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in _DWG_ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension '{ext}'. Allowed: {', '.join(sorted(_DWG_ALLOWED_EXTENSIONS))}",
        )

    # ── Save upload to a temp file with size limit (C-5 FIX) ────────────
    try:
        fd, temp_path = tempfile.mkstemp(
            suffix=ext, prefix="fireai_dwg_upload_"
        )
        os.close(fd)

        # Read upload content with size enforcement
        # FastAPI's UploadFile doesn't have .chunks() — use .read() instead
        contents = await file.read()
        if len(contents) > _MAX_DWG_SIZE_BYTES:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise HTTPException(
                status_code=413,
                detail=f"File too large (max {_MAX_DWG_SIZE_BYTES // (1024*1024)} MB). "
                       "Upload a smaller file or split the drawing.",
            )

        # ── Validate non-empty file ─────────────────────────────────────
        if not contents:
            raise HTTPException(
                status_code=422,
                detail={"success": False, "error": "Empty file uploaded"},
            )

        with open(temp_path, "wb") as f:
            f.write(contents)

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
        raise  # Re-raise HTTPExceptions (400, 422, 503) — don't convert to 500
    except Exception as exc:
        logger.error(
            "DWG parse request failed: %s: %s", type(exc).__name__, exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": f"Internal error: {type(exc).__name__}",
            },
        )
    finally:
        # ── Clean up temp file ─────────────────────────────────────────
        try:
            if "temp_path" in locals():
                os.unlink(temp_path)
        except Exception as exc:
            logger.debug("Temp file cleanup failed: %s", exc)
