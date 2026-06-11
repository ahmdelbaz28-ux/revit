"""
backend/routers/dwg.py — DWG/DXF file parsing endpoint.

Provides a single endpoint for uploading a DWG or DXF file and
receiving structured parsing results (room count, errors, etc.).

SAFETY: Input path validation is delegated to parsers._path_security
via DWGParser.parse(). The temp file is cleaned up after every request.
"""

from __future__ import annotations

import os
import tempfile
import logging

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/parse-dwg", tags=["dwg"])

_DWG_ALLOWED_EXTENSIONS = frozenset({".dwg", ".dxf"})


@router.post("")
async def parse_dwg(file: UploadFile = File(...)):
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

    # ── Save upload to a temp file ──────────────────────────────────────
    try:
        fd, temp_path = tempfile.mkstemp(
            suffix=ext, prefix="fireai_dwg_upload_"
        )
        os.close(fd)

        contents = await file.read()
        with open(temp_path, "wb") as f:
            f.write(contents)

        # ── Parse via DWGParser ─────────────────────────────────────────
        from parsers.dwg_parser import DWGParser

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
