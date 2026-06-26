"""
Authentication and authorization dependencies for FastAPI.

Provides FastAPI dependencies for extracting the current user's role
from the request and enforcing permission checks on endpoints.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from backend.rbac import Permission, Role, has_permission
from typing import Callable


def get_current_role(request: Request) -> Role:
    """
    Extract the current user's role from the request.

    The role is set by the ApiKeyMiddleware on request.state.fireai_role
    and also stored in request.scope["fireai_role"] as a fallback.

    If no role is found (e.g., whitelisted paths or development mode),
    defaults to VIEWER for safety (least privilege).
    """
    role = getattr(request.state, "fireai_role", None)
    if role is not None:
        return role
    # Fallback: check for role in request scope (set by ASGI middleware)
    role = request.scope.get("fireai_role")
    if role is not None:
        return role
    # Default to VIEWER (least privilege) when no role is set
    return Role.VIEWER


def require_permission(permission: Permission) -> Callable:
    """
    FastAPI dependency factory that requires a specific permission.

    Usage:
        @router.post("", dependencies=[Depends(require_permission(Permission.PROJECT_CREATE))])
        async def create_project(...):
            ...

    Raises HTTP 403 Forbidden if the current role lacks the required permission.
    """

    def checker(request: Request) -> Role:
        role = get_current_role(request)
        if not has_permission(role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(f"Permission denied: {permission.value} required. Your role: {role.value}"),
            )
        return role

    return checker
