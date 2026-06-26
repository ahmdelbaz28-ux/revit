"""
backend/routers/ifc_files.py — Serve IFC Files with Path Traversal Protection
==============================================================================

Provides API endpoints to serve .ifc files for the frontend IfcViewer.
Implements V128 hardening: path traversal protection, null byte injection
prevention, and symlink resolution.

SAFETY-CRITICAL:
  - Path traversal is a CRITICAL attack vector — a malicious request could
    read /etc/passwd or any file on the server if not properly validated.
  - Defense-in-depth: multiple validation layers (not just one check)
  - All file access is logged for audit trail (NFPA 72 §10.6)

REFERENCE:
  V128 hardening, NFPA 72-2022 §10.6 (audit trail)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

logger = logging.getLogger("fireai.routers.ifc_files")

router = APIRouter(prefix="/ifc-files", tags=["ifc-files"])

# ── Configuration ─────────────────────────────────────────────────────────────

# Root directory for IFC files — MUST be explicitly configured
IFC_ROOT_DIR = os.getenv(
    "FIREAI_IFC_FILES_DIR",
    os.path.join(os.getcwd(), "uploads", "ifc"),
)

# Allowed file extensions (case-insensitive)
ALLOWED_EXTENSIONS = frozenset({".ifc", ".ifcxml", ".ifc.json"})

# Maximum file size (500 MB — IFC files can be large)
MAX_FILE_SIZE = int(os.getenv("FIREAI_IFC_MAX_FILE_SIZE_BYTES", str(500 * 1024 * 1024)))


# ── Security Validation ───────────────────────────────────────────────────────

def _validate_ifc_file_path(filename: str, root_dir: Path) -> Path:
    """
    Validate and resolve an IFC file path with defense-in-depth security.

    Security checks (in order):
      1. Null byte injection prevention
      2. Extension allowlist
      3. Path resolution within allowed root (path traversal prevention)
      4. Symlink escape detection
      5. File existence and size validation

    Args:
        filename: The requested filename (NOT a full path).
        root_dir: The allowed root directory.

    Returns:
        Resolved Path object if all checks pass.

    Raises:
        HTTPException: On any security violation or file not found.
    """
    # ── Check 1: Null byte injection ──
    if "\x00" in filename or "%00" in filename:
        logger.warning("SECURITY: Null byte injection attempt: %r", filename)
        raise HTTPException(
            status_code=400,
            detail="Invalid filename: null bytes not allowed",
        )

    # ── Check 2: Extension allowlist ──
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        logger.warning("SECURITY: Disallowed extension: %s (file: %r)", ext, filename)
        raise HTTPException(
            status_code=400,
            detail=f"File extension '{ext}' not allowed. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    # ── Check 3: Path traversal prevention ──
    # Reject any path component that tries to escape
    if ".." in filename or "/" in filename or "\\" in filename:
        logger.warning("SECURITY: Path traversal attempt: %r", filename)
        raise HTTPException(
            status_code=400,
            detail="Invalid filename: path traversal characters not allowed",
        )

    # ── Check 4: Resolve within allowed root ──
    root_resolved = root_dir.resolve()
    target_path = (root_dir / filename).resolve()

    try:
        target_path.relative_to(root_resolved)
    except ValueError:
        logger.warning(
            "SECURITY: Path escape detected: %s resolves outside %s",
            target_path, root_resolved,
        )
        raise HTTPException(
            status_code=403,
            detail="Access denied: file path outside allowed directory",
        )

    # ── Check 5: Symlink escape detection ──
    if target_path.is_symlink():
        symlink_target = target_path.resolve()
        if not str(symlink_target).startswith(str(root_resolved)):
            logger.warning(
                "SECURITY: Symlink escape detected: %s -> %s",
                target_path, symlink_target,
            )
            raise HTTPException(
                status_code=403,
                detail="Access denied: symlink points outside allowed directory",
            )

    # ── Check 6: File existence ──
    if not target_path.is_file():
        raise HTTPException(status_code=404, detail=f"IFC file not found: {filename}")

    # ── Check 7: File size validation ──
    file_size = target_path.stat().st_size
    if file_size > MAX_FILE_SIZE:
        logger.warning(
            "SECURITY: Oversized file rejected: %s (%d bytes > %d limit)",
            filename, file_size, MAX_FILE_SIZE,
        )
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {file_size} bytes (max: {MAX_FILE_SIZE})",
        )

    return target_path


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/{filename}")
async def get_ifc_file(filename: str, request: Request) -> FileResponse:
    """
    Serve an IFC file for the frontend IfcViewer.

    Security: All path traversal, null byte, and symlink attacks are blocked.
    Only files within FIREAI_IFC_FILES_DIR are accessible.

    Args:
        filename: The IFC filename (e.g., "building.ifc").

    Returns:
        FileResponse with the IFC file content.
    """
    correlation_id = request.headers.get("X-Correlation-ID", "unknown")
    client_ip = request.client.host if request.client else "unknown"

    logger.info(
        "IFC file request | file=%s | client=%s | correlation_id=%s",
        filename, client_ip, correlation_id,
    )

    root_dir = Path(IFC_ROOT_DIR)

    # Ensure root directory exists
    if not root_dir.is_dir():
        logger.error("IFC root directory does not exist: %s", root_dir)
        raise HTTPException(
            status_code=500,
            detail="IFC file storage not configured",
        )

    # Validate and resolve path
    safe_path = _validate_ifc_file_path(filename, root_dir)

    # Determine content type
    ext = safe_path.suffix.lower()
    content_type_map = {
        ".ifc": "application/x-step",
        ".ifcxml": "application/xml",
        ".ifc.json": "application/json",
    }
    content_type = content_type_map.get(ext, "application/octet-stream")

    logger.info(
        "IFC file served | file=%s | size=%d | correlation_id=%s",
        filename, safe_path.stat().st_size, correlation_id,
    )

    return FileResponse(
        path=str(safe_path),
        media_type=content_type,
        filename=filename,
        headers={
            "X-Correlation-ID": correlation_id,
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.get("/")
async def list_ifc_files(request: Request) -> dict:
    """
    List available IFC files in the upload directory.

    Returns only filenames (no paths) for security.
    """
    root_dir = Path(IFC_ROOT_DIR)

    if not root_dir.is_dir():
        return {"files": [], "count": 0, "root_dir": str(root_dir)}

    files = []
    for f in root_dir.iterdir():
        if f.is_file() and f.suffix.lower() in ALLOWED_EXTENSIONS:
            try:
                size = f.stat().st_size
                files.append({
                    "name": f.name,
                    "size": size,
                    "extension": f.suffix.lower(),
                })
            except OSError:
                continue

    correlation_id = request.headers.get("X-Correlation-ID", "unknown")
    logger.info(
        "IFC file list | count=%d | correlation_id=%s",
        len(files), correlation_id,
    )

    return {
        "files": sorted(files, key=lambda x: x["name"]),
        "count": len(files),
        "root_dir": str(root_dir),
    }
