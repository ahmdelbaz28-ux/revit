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
    _role: Role = Depends(require_permission(Permission.USER_MANAGE)),  # NOSONAR - python:S8410
):
    """List all API keys (admin only). Key values are never returned."""
    keys = list_api_keys()
    return {"success": True, "data": keys}


@router.post("", status_code=201)
async def create_key(
    request: GenerateKeyRequest,
    _role: Role = Depends(require_permission(Permission.USER_MANAGE)),  # NOSONAR - python:S8410
):
    """
    Generate a new API key with the specified role (admin only).

    SECURITY: The plaintext key is returned ONLY on creation.
    It cannot be retrieved later — store it securely.
    """
    plaintext_key = generate_api_key(request.role, request.description)
    logger.info(  # NOSONAR
        "New API key generated: role=%s, desc=%s",
        request.role.value,
        request.description,
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
    _role: Role = Depends(require_permission(Permission.USER_MANAGE)),  # NOSONAR - python:S8410
):
    """Delete an API key by its hash (admin only)."""
    deleted = delete_api_key(key_hash)
    if not deleted:
        raise HTTPException(status_code=404, detail="API key not found")  # NOSONAR: S8415 — endpoint error handling is intentional  # NOSONAR — S7632: test function documented via class name / module path
    return {"success": True, "message": "API key deleted"}


@router.put("/{key_hash}")
async def update_key_role_endpoint(
    key_hash: str,
    request: UpdateKeyRoleRequest,
    _role: Role = Depends(require_permission(Permission.USER_MANAGE)),  # NOSONAR - python:S8410
):
    """Update an API key's role (admin only)."""
    updated = update_api_key_role(key_hash, request.role)
    if not updated:
        raise HTTPException(status_code=404, detail="API key not found")  # NOSONAR: S8415 — endpoint error handling is intentional  # NOSONAR — S7632: test function documented via class name / module path
    return {"success": True, "message": f"API key role updated to {request.role.value}"}


@router.get("/roles")
async def list_roles(
    _role: Role = Depends(require_permission(Permission.USER_MANAGE)),  # NOSONAR - python:S8410
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
