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
from backend.limiter import limiter, get_remote_address
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


# ── V151.1 Audit logging helper ──────────────────────────────────────────────
def _audit_key_event(event_type: str, key_id: str, masked_key: str, extra: dict | None = None) -> None:
    """
    Record a Vision API Keys event in the AuditStore for compliance traceability.

    Best-effort: never raises — if the AuditStore is unavailable (e.g. dev mode
    without ecdsa), the event is logged via the standard logger and skipped.
    This follows the same fail-safe pattern used in backend/audit_integrity_helper.py.
    """
    details = {"key_id": key_id, "masked_key": masked_key, "provider": "openai"}
    if extra:
        details.update(extra)
    try:
        from fireai.core.audit_store import AuditStore
        store = AuditStore()
        store.add_event(event_type=f"vision_key.{event_type}", room_id="global", details_dict=details)
    except Exception as e:
        # Fail-safe: log the event even if AuditStore is unavailable
        logger.debug("AuditStore unavailable for vision key event (%s): %s", event_type, type(e).__name__)


# ── Pydantic schemas ─────────────────────────────────────────────────────────


# V152: Supported providers — extensible list. Each provider has a default
# base_url and a default vision-capable model. The customer can override both.
SUPPORTED_PROVIDERS: dict[str, dict[str, str]] = {
    "openai": {
        "default_base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "test_path": "/models",
    },
    "anthropic": {
        "default_base_url": "https://api.anthropic.com/v1",
        "default_model": "claude-3-5-sonnet-20241022",
        "test_path": "/models",
    },
    "gemini": {
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta",
        "default_model": "gemini-2.0-flash",
        "test_path": "/models",
    },
    "azure": {
        "default_base_url": "",  # customer must provide their Azure endpoint
        "default_model": "gpt-4o",
        "test_path": "/models",
    },
    "openrouter": {
        "default_base_url": "https://openrouter.ai/api/v1",
        "default_model": "openai/gpt-4o",
        "test_path": "/models",
    },
    "opencode": {
        "default_base_url": "https://api.opencode.ai/v1",
        "default_model": "gpt-4o",
        "test_path": "/models",
    },
}


def _validate_provider(provider: str) -> str:
    """Validate the provider against the supported list. Returns the normalized provider name."""
    if not provider or not isinstance(provider, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider is required. Supported: {', '.join(SUPPORTED_PROVIDERS.keys())}",
        )
    normalized = provider.lower().strip()
    if normalized not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider '{provider}'. Supported: {', '.join(SUPPORTED_PROVIDERS.keys())}",
        )
    return normalized


class OpenAIKeyRequest(BaseModel):
    """Request body for storing a Vision API key (any supported provider)."""

    api_key: str = Field(
        ...,
        min_length=8,
        max_length=1024,
        description="The API key (e.g. sk-proj-...). Stored AES-256-GCM encrypted.",
    )
    base_url: str = Field(
        "",
        max_length=512,
        description="Provider base URL. If empty, uses the provider default.",
    )
    model_name: str = Field(
        "",
        max_length=128,
        description="Vision-capable model name. If empty, uses the provider default.",
    )
    description: str = Field(
        "",
        max_length=200,
        description="Optional human-readable label for the key (NOT stored encrypted).",
    )
    expires_at: Optional[str] = Field(
        None,
        description="Optional ISO 8601 expiry timestamp. After this date, the key is treated as inactive.",
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
    expires_at: Optional[str] = None
    is_expired: bool = False


class OpenAIKeyTestResponse(BaseModel):
    """Result of testing a stored key against the configured endpoint."""

    ok: bool
    status_code: Optional[int] = None
    error: Optional[str] = None
    masked_key: str


# ── Helpers ──────────────────────────────────────────────────────────────────


def _row_to_response(row) -> OpenAIKeyResponse:
    """Convert a DB row to a response object. NEVER decrypts."""
    # V152: safely read optional columns (expires_at may not exist on older DBs)
    row_keys = row.keys() if hasattr(row, 'keys') else []
    expires_at = row["expires_at"] if "expires_at" in row_keys else None
    description = row["description"] if "description" in row_keys else ""
    is_expired = _is_expired(expires_at)
    return OpenAIKeyResponse(
        id=row["id"],
        provider=row["provider"],
        masked_key=row["masked_key"],
        base_url=row["base_url"],
        model_name=row["model_name"],
        description=description,
        is_active=bool(row["is_active"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_used_at=row["last_used_at"],
        expires_at=expires_at,
        is_expired=is_expired,
    )


def _is_expired(expires_at: Optional[str]) -> bool:
    """Check if a key has expired. Returns False if expires_at is None or unparseable."""
    if not expires_at:
        return False
    try:
        from datetime import datetime, timezone
        # Handle both with and without timezone
        dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > dt
    except (ValueError, TypeError):
        return False  # unparseable → treat as not expired (fail-open for usability)


def _ensure_v152_columns() -> None:
    """V152: add expires_at column if missing (idempotent, like _ensure_description_column)."""
    _ensure_description_column()
    db = get_db()
    # Check if expires_at exists
    if db._is_postgres:
        with db._pg_cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='vision_api_keys' AND column_name='expires_at'"
            )
            exists = cur.fetchone() is not None
            if not exists:
                cur.execute("ALTER TABLE vision_api_keys ADD COLUMN expires_at TEXT")
                db._pg_conn.commit()
    else:
        with db._transaction() as cur:
            cur.execute("PRAGMA table_info(vision_api_keys)")
            cols = [r[1] for r in cur.fetchall()]
            if "expires_at" not in cols:
                cur.execute("ALTER TABLE vision_api_keys ADD COLUMN expires_at TEXT")


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
#
# V152: All endpoints are mounted under BOTH /openai (backward compat) and
# /{provider} (new generic path). The /openai routes simply delegate to the
# generic handlers with provider="openai". This preserves the V151 contract
# while enabling multi-provider support.


# V152: list all supported providers — MUST be registered BEFORE /{provider}
# to avoid the path parameter matching "providers" as a provider name.
@router.get("/providers/list")
async def list_supported_providers(
    _role=Depends(require_permission(Permission.SYSTEM_CONFIG)),
):
    """List all supported Vision API providers and their defaults."""
    return {"providers": SUPPORTED_PROVIDERS}


@router.post(
    "/{provider}",
    response_model=OpenAIKeyResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("10/minute", key_func=get_remote_address)
async def store_provider_key(
    request: Request,
    provider: str,
    body: OpenAIKeyRequest,
    _role=Depends(require_permission(Permission.SYSTEM_CONFIG)),
):
    """
    Store (encrypt + persist) a Vision API key for any supported provider.

    Supported providers: openai, anthropic, gemini, azure, openrouter, opencode.
    The /openai path is kept as a backward-compatible alias.

    The plaintext is encrypted with AES-256-GCM before persistence. Only the
    masked form (e.g. `fe_sk***...***f4c1`) is returned in the response.

    If an active key for the given provider already exists, it is deactivated
    (is_active=0) and the new key becomes the single active key.
    """
    provider = _validate_provider(provider)
    _ensure_v152_columns()
    # Apply provider defaults if customer didn't override
    prov_config = SUPPORTED_PROVIDERS[provider]
    base_url = body.base_url or prov_config["default_base_url"]
    model_name = body.model_name or prov_config["default_model"]
    if not base_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"base_url is required for provider '{provider}' (no default configured).",
        )

    db = get_db()
    now = utc_now_iso()
    key_id = str(uuid.uuid4())
    masked = mask_key(body.api_key)
    try:
        encrypted = encrypt_key(body.api_key)
    except ValueError as e:
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
                (now, provider),
            )
            # Insert the new active key (with optional expires_at)
            cur.execute(
                f"""INSERT INTO vision_api_keys
                   (id, provider, encrypted_key, masked_key, base_url, model_name,
                    is_active, created_at, updated_at, last_used_at, description, expires_at)
                   VALUES ({_ph()}, {_ph()}, {_ph()}, {_ph()}, {_ph()}, {_ph()},
                           1, {_ph()}, {_ph()}, NULL, {_ph()}, {_ph()})""",
                (
                    key_id,
                    provider,
                    encrypted,
                    masked,
                    base_url,
                    model_name,
                    now,
                    now,
                    body.description,
                    body.expires_at,
                ),
            )
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
        logger.error("Vision key inserted but not found on readback (id=%s)", key_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal inconsistency after key insertion.",
        )

    logger.info(
        "Stored %s Vision key id=%s masked=%s model=%s",
        provider, key_id, masked, model_name,
    )
    _audit_key_event("added", key_id, masked, {"provider": provider, "model_name": model_name, "base_url": base_url})
    return _row_to_response(row)


# V151 backward-compat alias: POST /openai → POST /{provider} with provider="openai"
@router.post(
    "/openai",
    response_model=OpenAIKeyResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
@limiter.limit("10/minute", key_func=get_remote_address)
async def store_openai_key_compat(
    request: Request,
    body: OpenAIKeyRequest,
    _role=Depends(require_permission(Permission.SYSTEM_CONFIG)),
):
    """Backward-compat alias for POST /openai → delegates to store_provider_key."""
    return await store_provider_key(request, "openai", body, _role)


@router.get("/{provider}", response_model=list[OpenAIKeyResponse])
async def list_provider_keys(
    provider: str,
    include_inactive: bool = False,
    _role=Depends(require_permission(Permission.SYSTEM_CONFIG)),
):
    """
    List stored Vision API keys for a given provider.

    Returns ONLY the masked form — never the plaintext. By default returns
    only active keys; pass `?include_inactive=true` to include deactivated ones.
    """
    provider = _validate_provider(provider)
    _ensure_v152_columns()
    db = get_db()
    try:
        with db._transaction() as cur:
            if include_inactive:
                cur.execute(
                    f"SELECT * FROM vision_api_keys WHERE provider = {_ph()} "
                    f"ORDER BY created_at DESC",
                    (provider,),
                )
            else:
                cur.execute(
                    f"SELECT * FROM vision_api_keys WHERE provider = {_ph()} AND is_active = 1 "
                    f"ORDER BY created_at DESC",
                    (provider,),
                )
            rows = cur.fetchall()
    except Exception as e:
        logger.error("Vision key list failed: %s", type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to list keys. The database is unavailable.",
        ) from e

    return [_row_to_response(r) for r in rows]


@router.get("/openai", response_model=list[OpenAIKeyResponse], include_in_schema=False)
async def list_openai_keys_compat(
    include_inactive: bool = False,
    _role=Depends(require_permission(Permission.SYSTEM_CONFIG)),
):
    """Backward-compat alias for GET /openai."""
    return await list_provider_keys("openai", include_inactive, _role)


@router.get("/{provider}/{key_id}", response_model=OpenAIKeyResponse)
async def get_provider_key(
    provider: str,
    key_id: str,
    _role=Depends(require_permission(Permission.SYSTEM_CONFIG)),
):
    """Get a single stored Vision API key (masked only)."""
    provider = _validate_provider(provider)
    _ensure_v152_columns()
    db = get_db()
    try:
        with db._transaction() as cur:
            cur.execute(
                f"SELECT * FROM vision_api_keys WHERE id = {_ph()} AND provider = {_ph()}",
                (key_id, provider),
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


@router.delete("/{provider}/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute", key_func=get_remote_address)
async def delete_provider_key(
    provider: str,
    key_id: str,
    request: Request,
    _role=Depends(require_permission(Permission.SYSTEM_CONFIG)),
):
    """
    Delete (revoke) a stored Vision API key.

    Idempotent: returns 204 whether the key existed or not.
    """
    provider = _validate_provider(provider)
    _ensure_v152_columns()
    db = get_db()
    masked_for_audit = ""
    try:
        with db._transaction() as cur:
            cur.execute(
                f"SELECT masked_key FROM vision_api_keys WHERE id = {_ph()} AND provider = {_ph()}",
                (key_id, provider),
            )
            row = cur.fetchone()
            if row is not None:
                masked_for_audit = row["masked_key"]
            cur.execute(
                f"DELETE FROM vision_api_keys WHERE id = {_ph()} AND provider = {_ph()}",
                (key_id, provider),
            )
    except Exception as e:
        logger.error("Vision key delete failed: %s", type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to delete the key. The database is unavailable.",
        ) from e

    logger.info("Deleted %s Vision key id=%s", provider, key_id)
    _audit_key_event("deleted", key_id, masked_for_audit or "unknown", {"provider": provider})
    return None


# V152: Bulk delete — delete all keys for a provider, or specific ids
class BulkDeleteRequest(BaseModel):
    """Request body for bulk-delete endpoint."""
    ids: Optional[list[str]] = Field(
        None,
        description="List of key IDs to delete. If omitted, deletes ALL keys for the provider.",
    )


@router.post("/{provider}/bulk-delete", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute", key_func=get_remote_address)
async def bulk_delete_provider_keys(
    provider: str,
    request: Request,
    body: BulkDeleteRequest,
    _role=Depends(require_permission(Permission.SYSTEM_CONFIG)),
):
    """
    Bulk-delete Vision API keys for a provider.

    - If `ids` is provided: deletes only those specific keys.
    - If `ids` is omitted/empty: deletes ALL keys for the provider (active + inactive).

    Returns the count of deleted keys. Idempotent — deleting non-existent ids
    counts as 0 (no error).
    """
    provider = _validate_provider(provider)
    _ensure_v152_columns()
    db = get_db()
    deleted_count = 0
    deleted_masks: list[str] = []
    try:
        with db._transaction() as cur:
            if body.ids:
                # Delete specific ids for this provider
                placeholders = ", ".join([_ph()] * len(body.ids))
                cur.execute(
                    f"SELECT masked_key FROM vision_api_keys WHERE id IN ({placeholders}) AND provider = {_ph()}",
                    (*body.ids, provider),
                )
                for r in cur.fetchall():
                    deleted_masks.append(r["masked_key"])
                cur.execute(
                    f"DELETE FROM vision_api_keys WHERE id IN ({placeholders}) AND provider = {_ph()}",
                    (*body.ids, provider),
                )
                deleted_count = cur.rowcount if hasattr(cur, 'rowcount') else len(deleted_masks)
            else:
                # Delete ALL keys for this provider
                cur.execute(
                    f"SELECT masked_key FROM vision_api_keys WHERE provider = {_ph()}",
                    (provider,),
                )
                for r in cur.fetchall():
                    deleted_masks.append(r["masked_key"])
                cur.execute(
                    f"DELETE FROM vision_api_keys WHERE provider = {_ph()}",
                    (provider,),
                )
                deleted_count = len(deleted_masks)
    except Exception as e:
        logger.error("Vision key bulk-delete failed: %s", type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to bulk-delete keys. The database is unavailable.",
        ) from e

    logger.info("Bulk-deleted %d %s Vision keys", deleted_count, provider)
    for m in deleted_masks:
        _audit_key_event("bulk_deleted", "bulk", m, {"provider": provider})
    return {"deleted_count": deleted_count, "provider": provider}


@router.post("/{provider}/{key_id}/test", response_model=OpenAIKeyTestResponse)
@limiter.limit("5/minute", key_func=get_remote_address)
async def test_provider_key(
    provider: str,
    key_id: str,
    request: Request,
    _role=Depends(require_permission(Permission.SYSTEM_CONFIG)),
):
    """
    Test a stored Vision API key by pinging {base_url}/models.

    Returns pass/fail + status code. Does NOT auto-delete on failure.

    Uses a 10-second timeout. If the endpoint is unreachable, returns ok=false
    with a generic error message (no internal network details leaked).
    """
    provider = _validate_provider(provider)
    _ensure_v152_columns()
    db = get_db()
    try:
        with db._transaction() as cur:
            cur.execute(
                f"SELECT * FROM vision_api_keys WHERE id = {_ph()} AND provider = {_ph()} AND is_active = 1",
                (key_id, provider),
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
    prov_config = SUPPORTED_PROVIDERS.get(provider, {})
    default_base = prov_config.get("default_base_url", "https://api.openai.com/v1")
    base_url = (row["base_url"] or default_base).rstrip("/")
    test_path = prov_config.get("test_path", "/models")

    # V152: skip test if key is expired
    row_keys = row.keys() if hasattr(row, 'keys') else []
    expires_at = row["expires_at"] if "expires_at" in row_keys else None
    if _is_expired(expires_at):
        return OpenAIKeyTestResponse(
            ok=False,
            status_code=None,
            error="Key has expired. Please update or delete it.",
            masked_key=masked,
        )

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

    try:
        with db._transaction() as cur:
            cur.execute(
                f"UPDATE vision_api_keys SET last_used_at = {_ph()} WHERE id = {_ph()}",
                (utc_now_iso(), key_id),
            )
    except Exception as e:
        logger.debug("Failed to update last_used_at for id=%s: %s", key_id, type(e).__name__)

    test_url = f"{base_url}{test_path}"
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


# V151 backward-compat aliases for GET-id, DELETE, test (all delegate to generic handlers)
@router.get("/openai/{key_id}", response_model=OpenAIKeyResponse, include_in_schema=False)
async def get_openai_key_compat(
    key_id: str,
    _role=Depends(require_permission(Permission.SYSTEM_CONFIG)),
):
    """Backward-compat alias for GET /openai/{id}."""
    return await get_provider_key("openai", key_id, _role)


@router.delete("/openai/{key_id}", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False)
@limiter.limit("10/minute", key_func=get_remote_address)
async def delete_openai_key_compat(
    key_id: str,
    request: Request,
    _role=Depends(require_permission(Permission.SYSTEM_CONFIG)),
):
    """Backward-compat alias for DELETE /openai/{id}."""
    return await delete_provider_key("openai", key_id, request, _role)


@router.post("/openai/{key_id}/test", response_model=OpenAIKeyTestResponse, include_in_schema=False)
@limiter.limit("5/minute", key_func=get_remote_address)
async def test_openai_key_compat(
    key_id: str,
    request: Request,
    _role=Depends(require_permission(Permission.SYSTEM_CONFIG)),
):
    """Backward-compat alias for POST /openai/{id}/test."""
    return await test_provider_key("openai", key_id, request, _role)


__all__ = ["router", "SUPPORTED_PROVIDERS"]
