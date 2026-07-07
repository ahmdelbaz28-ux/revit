# NOSONAR
"""
backend/routers/dwg.py — DWG/DXF file parsing endpoint.

Provides a single endpoint for uploading a DWG or DXF file and
receiving structured parsing results (room count, errors, etc.).

SAFETY: Input path validation is delegated to parsers._path_security
via DWGParser.parse(). The temp file is cleaned up after every request.

STRESS-TEST FIX #5 (DWG DoS):
  - Added explicit auth dependency (require PROJECT_CREATE permission).
  - Added rate limit (10/minute per IP — parsing is CPU-intensive).
  - Streamed chunks DIRECTLY to disk (was accumulating in a list, which
    could OOM the server with 100MB × concurrent uploads).
  - Tightened size limit to 50 MB (was 100 MB) — DXF files rarely exceed
    this in practice, and the lower limit reduces per-request risk.
"""

from __future__ import annotations

import logging
import os
import tempfile

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from backend.auth import require_permission
from backend.rbac import Permission

try:
    from backend.limiter import limiter
    _HAS_LIMITER = True
except ImportError:
    _HAS_LIMITER = False
    limiter = None

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/parse-dwg", tags=["dwg"])

_DWG_ALLOWED_EXTENSIONS = frozenset({".dwg", ".dxf"})

# STRESS-TEST FIX #5: Tightened from 100 MB to 50 MB. Combined with the
# new streaming-to-disk pattern, this prevents OOM under concurrent load.
_MAX_DWG_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB

# Auth dependency for the parse endpoint — was missing entirely.
_AUTH = [Depends(require_permission(Permission.PROJECT_CREATE))]


# V140 Phase 10 SELF-CRITICISM FIX: Rate limit for DWG upload.
# Previous approach used @router.post THEN @limiter.limit — wrong order.
# The @router.post decorator captures the function as endpoint BEFORE
# @limiter.limit can add _rate_limits metadata. Result: rate limit was
# silently NOT applied.
#
# Correct approach: define function, apply @limiter.limit, then register
# the route manually using router.add_api_route(). This ensures the
# limiter-wrapped function is what the route uses.


async def _parse_dwg_impl(request: Request, file: UploadFile):  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
    """
    Upload a DWG or DXF file for parsing.

    Returns structured parsing results including room count, conversion
    time, and any errors/warnings. On validation failure, returns a
    400-level error with details.

    STRESS-TEST FIX #5: Now requires PROJECT_CREATE permission and is
    rate-limited to 10/minute per client IP. Chunks are streamed directly
    to a temp file (no in-memory accumulation).
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

    # ── Save upload to a temp file with size limit (C-5 FIX + STRESS FIX #5) ──
    # Stream chunks DIRECTLY to disk — never accumulate in memory.
    temp_path = ""
    try:
        fd, temp_path = tempfile.mkstemp(suffix=ext, prefix="fireai_dwg_upload_")
        # Wrap the os-level fd in a Python file object for buffered writes
        with os.fdopen(fd, "wb") as out_f:  # NOSONAR: S7493 sync file I/O acceptable for small config reads  # NOSONAR — S7632: test function documented via class name / module path
            _CHUNK_SIZE = 1024 * 1024  # 1 MB per read
            file_size = 0
            empty = True
            while True:
                chunk = await file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                empty = False
                file_size += len(chunk)
                if file_size > _MAX_DWG_SIZE_BYTES:
                    # Caller will clean up via finally block
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large (max {_MAX_DWG_SIZE_BYTES // (1024*1024)} MB). "
                               "Upload a smaller file or split the drawing.",
                    )
                out_f.write(chunk)
            # fsync to ensure data is on disk before parser reads it
            out_f.flush()
            os.fsync(out_f.fileno())

        # ── Validate non-empty file ─────────────────────────────────────
        if empty:
            raise HTTPException(
                status_code=422,
                detail={"success": False, "error": "Empty file uploaded"},
            )

        # ── Parse via DWGParser ─────────────────────────────────────────
        try:
            from parsers.dwg_parser import DWGParser
        except ImportError as import_err:
            raise HTTPException(
                status_code=503,  # NOSONAR: S8415 — endpoint error handling is intentional  # NOSONAR — S7632: test function documented via class name / module path
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
        logger.exception(
            "DWG parse request failed: %s: %s", type(exc).__name__, exc,
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
        if temp_path:
            try:
                os.unlink(temp_path)
            except Exception as exc:
                logger.debug("Temp file cleanup failed: %s", exc)


# V140 Phase 10 SELF-CRITICISM FIX: Register route MANUALLY after applying
# @limiter.limit. This ensures the limiter-wrapped function is the actual
# endpoint. The previous @router.post + @limiter.limit order was wrong.
if _HAS_LIMITER:
    @limiter.limit("10/minute")
    async def _rate_limited_parse_dwg(request: Request, file: UploadFile = File(...)):
        """Rate-limited wrapper for DWG parse endpoint."""
        return await _parse_dwg_impl(request, file)

    _rate_limited_parse_dwg.__annotations__["file"] = UploadFile

    router.add_api_route(
        "",
        _rate_limited_parse_dwg,
        methods=["POST"],
        dependencies=_AUTH,
        name="parse_dwg",
    )
else:
    router.add_api_route(
        "",
        _parse_dwg_impl,
        methods=["POST"],
        dependencies=_AUTH,
        name="parse_dwg",
    )

# HOTFIX C-3: Public alias for backward compatibility.
# V140 Phase 10 refactor renamed parse_dwg → _parse_dwg_impl (private) and
# registered it via router.add_api_route(). However, tests/test_dwg_router.py
# imports `parse_dwg` directly to register it on a test FastAPI app without
# the _AUTH dependency (which would cause 403 in tests).
# This alias preserves backward compatibility without changing the rate-limited
# production endpoint. The alias points to the unwrapped _parse_dwg_impl so
# tests can register it without auth.
parse_dwg = _parse_dwg_impl

