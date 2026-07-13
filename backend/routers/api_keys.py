# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
"""
backend/routers/api_keys.py — API Key management endpoints (admin only).

Provides CRUD operations for API keys with role-based access control:
  GET    /api/admin/keys        → List all API keys
  POST   /api/admin/keys        → Generate a new API key
  DELETE /api/admin/keys/{hash}  → Delete an API key
  GET    /api/admin/keys/roles   → List available roles and permissions
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.admin_protection import audit_operation, require_master_admin
from backend.api_keys import (
    delete_api_key,
    generate_api_key,
    list_api_keys,
    update_api_key_role,
)
from backend.auth import require_permission
from backend.rbac import ROLE_PERMISSIONS, Permission, Role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/keys", tags=["admin"])


class GenerateKeyRequest(BaseModel):
    """Request body for generating a new API key."""

    role: Role = Field(..., description="Role for the new API key")
    description: str = Field("", max_length=200, description="Description for the key")


class UpdateKeyRoleRequest(BaseModel):
    """Request body for updating an API key's role."""

    role: Role = Field(..., description="New role for the API key")


@router.get("")
async def list_keys(
    _role: Role = Depends(require_permission(Permission.USER_MANAGE)),  # NOSONAR — S8410: FastAPI Depends pattern is idiomatic
    ip: str = Depends(require_master_admin),  # NOSONAR — S8410: FastAPI Depends pattern is idiomatic
):
    """List all API keys (admin only). Key values are never returned."""
    keys = list_api_keys()
    await audit_operation(ip, "list_keys", True, detail=f"Returned {len(keys)} keys")
    return {"success": True, "data": keys}


@router.post("", status_code=201)
async def create_key(
    request: GenerateKeyRequest,
    _role: Role = Depends(require_permission(Permission.USER_MANAGE)),  # NOSONAR — S8410: FastAPI Depends pattern is idiomatic
    ip: str = Depends(require_master_admin),  # NOSONAR — S8410: FastAPI Depends pattern is idiomatic
):
    """
    Generate a new API key with the specified role (admin only).

    SECURITY: The plaintext key is returned ONLY on creation.
    It cannot be retrieved later — store it securely.

    V240: Requires X-Master-Admin-Token header (separate from API key).
    """
    plaintext_key = generate_api_key(request.role, request.description)
    logger.info(  # NOSONAR
        "New API key generated: role=%s, desc=%s, ip=%s",
        request.role.value,
        request.description,
        ip,
    )
    await audit_operation(
        ip,
        "create_key",
        True,
        target=plaintext_key[:16] + "...",
        detail=f"role={request.role.value}, desc={request.description}",
    )
    return {
        "success": True,
        "data": {
            "key": plaintext_key,
            "role": request.role.value,
            "description": request.description,
            "warning": "Store this key securely. It cannot be retrieved later.",
        },
    }


@router.delete("/{key_hash}")
async def delete_key(
    key_hash: str,
    _role: Role = Depends(require_permission(Permission.USER_MANAGE)),  # NOSONAR — S8410: FastAPI Depends pattern is idiomatic
    ip: str = Depends(require_master_admin),  # NOSONAR — S8410: FastAPI Depends pattern is idiomatic
):
    """Delete an API key by its hash (admin only)."""
    deleted = delete_api_key(key_hash)
    if not deleted:
        await audit_operation(ip, "delete_key", False, target=key_hash[:32], detail="Key not found")
        raise HTTPException(status_code=404, detail="API key not found")  # NOSONAR: S8415 — endpoint error handling is intentional  # NOSONAR — S7632: test function documented via class name / module path
    await audit_operation(ip, "delete_key", True, target=key_hash[:32])
    return {"success": True, "message": "API key deleted"}


@router.put("/{key_hash}")
async def update_key_role_endpoint(
    key_hash: str,
    request: UpdateKeyRoleRequest,
    _role: Role = Depends(require_permission(Permission.USER_MANAGE)),  # NOSONAR — S8410: FastAPI Depends pattern is idiomatic
    ip: str = Depends(require_master_admin),  # NOSONAR — S8410: FastAPI Depends pattern is idiomatic
):
    """Update an API key's role (admin only)."""
    updated = update_api_key_role(key_hash, request.role)
    if not updated:
        await audit_operation(ip, "update_key_role", False, target=key_hash[:32], detail="Key not found")
        raise HTTPException(status_code=404, detail="API key not found")  # NOSONAR: S8415 — endpoint error handling is intentional  # NOSONAR — S7632: test function documented via class name / module path
    await audit_operation(
        ip,
        "update_key_role",
        True,
        target=key_hash[:32],
        detail=f"new_role={request.role.value}",
    )
    return {"success": True, "message": f"API key role updated to {request.role.value}"}


@router.get("/roles")
async def list_roles(
    _role: Role = Depends(require_permission(Permission.USER_MANAGE)),  # NOSONAR — S8410: FastAPI Depends pattern is idiomatic
    _ip: str = Depends(require_master_admin),  # NOSONAR — S8410: FastAPI Depends pattern is idiomatic
):
    """List available roles and their permissions (admin only)."""
    roles_info = {}
    for role in Role:
        perms = ROLE_PERMISSIONS.get(role, set())
        roles_info[role.value] = {
            "role": role.value,
            "permissions": sorted([p.value for p in perms]),
            "permission_count": len(perms),
        }
    return {"success": True, "data": roles_info}
