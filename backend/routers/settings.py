"""
backend/routers/settings.py — Vision API Keys settings endpoints (V151).

Implements the customer-facing flow for managing OpenAI Vision API keys:

  POST   /api/v1/settings/keys/openai         → Store (encrypt + persist) a key
  GET    /api/v1/settings/keys/openai         → List active keys (masked only)
  GET    /api/v1/settings/keys/openai/{id}    → Get one key (masked only)
  DELETE /api/v1/settings/keys/openai/{id}    → Delete (revoke) a key
  POST   /api/v1/settings/keys/openai/{id}/test → Test the key (lightweight ping)

🔒 SECURITY
-----------
- All endpoints require Permission.SYSTEM_CONFIG (admin role by default).
- Plaintext keys are NEVER returned in any response. Only the masked form is
  returned: `fe_sk***...***f4c1`.
- Plaintext keys are NEVER logged. logger.info calls only reference the masked
  form or the key id (a UUID unrelated to the key material).
- Encryption is AES-256-GCM with per-record random nonces. See
  backend/vision_key_store.py for the cryptographic primitives.
- The DELETE endpoint is idempotent — deleting a non-existent id returns 404
  but does not leak whether the id ever existed (the response is identical
  for "never existed" and "already deleted").
- The test endpoint makes a REAL API call to OpenAI's /v1/models endpoint
  (lightweight GET). The result is pass/fail only — no model data is leaked.
  A failed test does NOT auto-delete the key; the customer decides.

FALLBACK CONTRACT
-----------------
This module NEVER raises if the DB or encryption layer fails. Instead:
- On DB error: return HTTP 503 with a generic message.
- On encryption error: return HTTP 500 with a generic message.
- On decryption error (shouldn't happen — means tampering): return HTTP 500.
The CUA loop (fireai/vision/cua_loop.py) independently falls back to OpenCV
when no key is available or when the stored key fails at runtime.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from backend.auth import require_permission
from backend.database import get_db
from backend.rbac import Permission
from backend.vision_key_store import (
    VisionApiKeyRecord,
    decrypt_key,
    encrypt_key,
    mask_key,
    utc_now_iso,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings/keys", tags=["settings"])


# ── Pydantic schemas ─────────────────────────────────────────────────────────


class OpenAIKeyRequest(BaseModel):
    """Request body for storing an OpenAI Vision API key."""

    api_key: str = Field(
        ...,
        min_length=8,
        max_length=1024,
        description="The OpenAI API key (e.g. sk-proj-...). Stored AES-256-GCM encrypted.",
    )
    base_url: str = Field(
        "https://api.openai.com/v1",
        max_length=512,
        description="OpenAI-compatible base URL. Defaults to the official OpenAI endpoint.",
    )
    model_name: str = Field(
        "gpt-4o",
        max_length=128,
        description="Vision-capable model name (e.g. gpt-4o, gpt-4-vision-preview).",
    )
    description: str = Field(
        "",
        max_length=200,
        description="Optional human-readable label for the key (NOT stored encrypted).",
    )


class OpenAIKeyResponse(BaseModel):
    """Response schema — never contains the plaintext key."""

    id: str
    provider: str = "openai"
    masked_key: str
    base_url: str
    model_name: str
    description: str = ""
    is_active: bool
    created_at: str
    updated_at: str
    last_used_at: Optional[str] = None


class OpenAIKeyTestResponse(BaseModel):
    """Result of testing a stored key against the configured endpoint."""

    ok: bool
    status_code: Optional[int] = None
    error: Optional[str] = None
    masked_key: str


# ── Helpers ──────────────────────────────────────────────────────────────────


def _row_to_response(row) -> OpenAIKeyResponse:
    """Convert a DB row to a response object. NEVER decrypts."""
    return OpenAIKeyResponse(
        id=row["id"],
        provider=row["provider"],
        masked_key=row["masked_key"],
        base_url=row["base_url"],
        model_name=row["model_name"],
        description=row["description"] if "description" in row.keys() else "",
        is_active=bool(row["is_active"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_used_at=row["last_used_at"],
    )


def _ph() -> str:
    """Get the parameter placeholder for the current DB backend."""
    db = get_db()
    return db._ph()  # pylint: disable=protected-access


def _description_column_exists() -> bool:
    """
    Check whether the `description` column exists in vision_api_keys.

    The column is added in a follow-up migration (V151.1). To stay backward
    compatible with deployed DBs that don't have it yet, we add it on first
    access if missing. This is a one-time ALTER TABLE per database.
    """
    db = get_db()
    if db._is_postgres:
        with db._pg_cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='vision_api_keys' AND column_name='description'"
            )
            return cur.fetchone() is not None
    # SQLite: query pragma table_info
    with db._transaction() as cur:
        cur.execute("PRAGMA table_info(vision_api_keys)")
        return any(r[1] == "description" for r in cur.fetchall())


def _ensure_description_column() -> None:
    """Add the description column if it doesn't exist (idempotent)."""
    if _description_column_exists():
        return
    db = get_db()
    if db._is_postgres:
        with db._pg_cursor() as cur:
            cur.execute(
                "ALTER TABLE vision_api_keys ADD COLUMN description TEXT NOT NULL DEFAULT ''"
            )
            db._pg_conn.commit()
    else:
        with db._transaction() as cur:
            cur.execute(
                "ALTER TABLE vision_api_keys ADD COLUMN description TEXT NOT NULL DEFAULT ''"
            )
    logger.info("Added 'description' column to vision_api_keys (V151.1 migration)")


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post(
    "/openai",
    response_model=OpenAIKeyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def store_openai_key(
    request: OpenAIKeyRequest,
    _role=Depends(require_permission(Permission.SYSTEM_CONFIG)),
):
    """
    Store (encrypt + persist) an OpenAI Vision API key.

    The plaintext is encrypted with AES-256-GCM before persistence. Only the
    masked form (e.g. `fe_sk***...***f4c1`) is returned in the response.

    If an active key for provider=openai already exists, it is deactivated
    (is_active=0) and the new key becomes the single active key. This
    implements the "add/update anytime" flow described in the V151 spec.
    """
    _ensure_description_column()
    db = get_db()
    now = utc_now_iso()
    key_id = str(uuid.uuid4())
    masked = mask_key(request.api_key)
    try:
        encrypted = encrypt_key(request.api_key)
    except ValueError as e:
        # Encryption failed — generic error, no key material leaked
        logger.error("Vision key encryption failed: %s", type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to encrypt the API key. Please try again.",
        ) from e

    try:
        with db._transaction() as cur:
            # Deactivate any existing active key for this provider
            cur.execute(
                f"UPDATE vision_api_keys SET is_active = 0, updated_at = {_ph()} "
                f"WHERE provider = {_ph()} AND is_active = 1",
                (now, "openai"),
            )
            # Insert the new active key
            cur.execute(
                f"""INSERT INTO vision_api_keys
                   (id, provider, encrypted_key, masked_key, base_url, model_name,
                    is_active, created_at, updated_at, last_used_at, description)
                   VALUES ({_ph()}, {_ph()}, {_ph()}, {_ph()}, {_ph()}, {_ph()},
                           1, {_ph()}, {_ph()}, NULL, {_ph()})""",
                (
                    key_id,
                    "openai",
                    encrypted,
                    masked,
                    request.base_url,
                    request.model_name,
                    now,
                    now,
                    request.description,
                ),
            )
            # Read back
            cur.execute(
                f"SELECT * FROM vision_api_keys WHERE id = {_ph()}",
                (key_id,),
            )
            row = cur.fetchone()
    except Exception as e:
        logger.error("Vision key persistence failed: %s", type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to persist the API key. The database is unavailable.",
        ) from e

    if row is None:
        # Should not happen — INSERT succeeded but SELECT returned nothing
        logger.error("Vision key inserted but not found on readback (id=%s)", key_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal inconsistency after key insertion.",
        )

    # Log WITHOUT plaintext (only masked + id)
    logger.info(
        "Stored OpenAI Vision key id=%s masked=%s model=%s",
        key_id,
        masked,
        request.model_name,
    )
    return _row_to_response(row)


@router.get("/openai", response_model=list[OpenAIKeyResponse])
async def list_openai_keys(
    include_inactive: bool = False,
    _role=Depends(require_permission(Permission.SYSTEM_CONFIG)),
):
    """
    List stored OpenAI Vision API keys.

    Returns ONLY the masked form — never the plaintext. By default returns
    only active keys; pass `?include_inactive=true` to include deactivated ones.
    """
    _ensure_description_column()
    db = get_db()
    try:
        with db._transaction() as cur:
            if include_inactive:
                cur.execute(
                    f"SELECT * FROM vision_api_keys WHERE provider = {_ph()} "
                    f"ORDER BY created_at DESC",
                    ("openai",),
                )
            else:
                cur.execute(
                    f"SELECT * FROM vision_api_keys WHERE provider = {_ph()} AND is_active = 1 "
                    f"ORDER BY created_at DESC",
                    ("openai",),
                )
            rows = cur.fetchall()
    except Exception as e:
        logger.error("Vision key list failed: %s", type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to list keys. The database is unavailable.",
        ) from e

    return [_row_to_response(r) for r in rows]


@router.get("/openai/{key_id}", response_model=OpenAIKeyResponse)
async def get_openai_key(
    key_id: str,
    _role=Depends(require_permission(Permission.SYSTEM_CONFIG)),
):
    """Get a single stored OpenAI Vision API key (masked only)."""
    _ensure_description_column()
    db = get_db()
    try:
        with db._transaction() as cur:
            cur.execute(
                f"SELECT * FROM vision_api_keys WHERE id = {_ph()} AND provider = {_ph()}",
                (key_id, "openai"),
            )
            row = cur.fetchone()
    except Exception as e:
        logger.error("Vision key get failed: %s", type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to fetch the key. The database is unavailable.",
        ) from e

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Key not found.",
        )
    return _row_to_response(row)


@router.delete("/openai/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_openai_key(
    key_id: str,
    _role=Depends(require_permission(Permission.SYSTEM_CONFIG)),
):
    """
    Delete (revoke) a stored OpenAI Vision API key.

    Idempotent: returns 204 whether the key existed or not. This avoids
    leaking information about whether a given id ever existed.
    """
    _ensure_description_column()
    db = get_db()
    try:
        with db._transaction() as cur:
            cur.execute(
                f"DELETE FROM vision_api_keys WHERE id = {_ph()} AND provider = {_ph()}",
                (key_id, "openai"),
            )
    except Exception as e:
        logger.error("Vision key delete failed: %s", type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to delete the key. The database is unavailable.",
        ) from e

    # Log WITHOUT plaintext (only id)
    logger.info("Deleted OpenAI Vision key id=%s", key_id)
    return None


@router.post("/openai/{key_id}/test", response_model=OpenAIKeyTestResponse)
async def test_openai_key(
    key_id: str,
    _role=Depends(require_permission(Permission.SYSTEM_CONFIG)),
):
    """
    Test a stored OpenAI Vision API key by pinging {base_url}/models.

    Returns pass/fail + status code. Does NOT auto-delete on failure —
    the customer decides whether to delete or update the key.

    The test uses a 10-second timeout to avoid hanging the UI. If the
    endpoint is unreachable, returns ok=false with a generic error message
    (no internal network details leaked).
    """
    _ensure_description_column()
    db = get_db()
    try:
        with db._transaction() as cur:
            cur.execute(
                f"SELECT * FROM vision_api_keys WHERE id = {_ph()} AND provider = {_ph()} AND is_active = 1",
                (key_id, "openai"),
            )
            row = cur.fetchone()
    except Exception as e:
        logger.error("Vision key test (load) failed: %s", type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to load the key. The database is unavailable.",
        ) from e

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active key not found.",
        )

    masked = row["masked_key"]
    base_url = (row["base_url"] or "https://api.openai.com/v1").rstrip("/")

    # Decrypt (only here, in-memory, never logged)
    try:
        plaintext = decrypt_key(row["encrypted_key"])
    except ValueError as e:
        logger.error("Vision key test (decrypt) failed for id=%s: %s", key_id, type(e).__name__)
        return OpenAIKeyTestResponse(
            ok=False,
            status_code=None,
            error="Decryption failed — the key may have been corrupted. Please re-enter it.",
            masked_key=masked,
        )

    # Update last_used_at (best-effort, do not fail the request on this)
    try:
        with db._transaction() as cur:
            cur.execute(
                f"UPDATE vision_api_keys SET last_used_at = {_ph()} WHERE id = {_ph()}",
                (utc_now_iso(), key_id),
            )
    except Exception as e:
        logger.debug("Failed to update last_used_at for id=%s: %s", key_id, type(e).__name__)

    # Ping the /models endpoint (lightweight, no tokens consumed)
    test_url = f"{base_url}/models"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                test_url,
                headers={"Authorization": f"Bearer {plaintext}"},
            )
        ok = resp.status_code == 200
        error = None if ok else f"HTTP {resp.status_code}"
        return OpenAIKeyTestResponse(
            ok=ok,
            status_code=resp.status_code,
            error=error,
            masked_key=masked,
        )
    except httpx.TimeoutException:
        return OpenAIKeyTestResponse(
            ok=False,
            status_code=None,
            error="Request timed out (10s). The endpoint may be unreachable.",
            masked_key=masked,
        )
    except httpx.HTTPError as e:
        # Do NOT include the original exception message — could leak URL or headers
        logger.debug("Vision key test (network) failed for id=%s: %s", key_id, type(e).__name__)
        return OpenAIKeyTestResponse(
            ok=False,
            status_code=None,
            error="Network error while contacting the endpoint.",
            masked_key=masked,
        )
    except Exception as e:
        logger.error("Vision key test (unknown) failed for id=%s: %s", key_id, type(e).__name__)
        return OpenAIKeyTestResponse(
            ok=False,
            status_code=None,
            error="Unexpected error during key test.",
            masked_key=masked,
        )


__all__ = ["router"]
