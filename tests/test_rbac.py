"""Tests for the Role-Based Access Control (RBAC) system.

Tests cover:
  - Role-permission mapping correctness
  - Admin has all permissions
  - Engineer cannot access system config or user management
  - Viewer cannot create/update/delete anything
  - API keys with different roles get appropriate access
  - Permission denied returns 403
  - API key CRUD operations
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, Depends, HTTPException
from fastapi.testclient import TestClient

# ── Unit tests for RBAC models ──────────────────────────────────────────────


class TestRBACModels:
    """Test the RBAC role and permission models."""

    def test_admin_has_all_permissions(self):
        """Admin role should have every permission defined."""
        from backend.rbac import Role, Permission, ROLE_PERMISSIONS

        admin_perms = ROLE_PERMISSIONS[Role.ADMIN]
        all_perms = set(Permission.__members__.values())
        assert admin_perms == all_perms, (
            f"Admin is missing permissions: {all_perms - admin_perms}"
        )

    def test_engineer_cannot_manage_users_or_system(self):
        """Engineer should NOT have USER_MANAGE or SYSTEM_CONFIG permissions."""
        from backend.rbac import Role, Permission, has_permission

        assert not has_permission(Role.ENGINEER, Permission.USER_MANAGE)
        assert not has_permission(Role.ENGINEER, Permission.SYSTEM_CONFIG)

    def test_engineer_can_create_edit_delete_projects(self):
        """Engineer should be able to create, edit, and delete projects."""
        from backend.rbac import Role, Permission, has_permission

        assert has_permission(Role.ENGINEER, Permission.PROJECT_READ)
        assert has_permission(Role.ENGINEER, Permission.PROJECT_CREATE)
        assert has_permission(Role.ENGINEER, Permission.PROJECT_UPDATE)
        assert has_permission(Role.ENGINEER, Permission.PROJECT_DELETE)

    def test_engineer_can_run_calculations_and_reports(self):
        """Engineer should be able to run calculations and generate reports."""
        from backend.rbac import Role, Permission, has_permission

        assert has_permission(Role.ENGINEER, Permission.CALCULATION_EXECUTE)
        assert has_permission(Role.ENGINEER, Permission.REPORT_GENERATE)
        assert has_permission(Role.ENGINEER, Permission.QOMN_EXECUTE)
        assert has_permission(Role.ENGINEER, Permission.FACP_MANAGE)

    def test_viewer_read_only(self):
        """Viewer should have ONLY read permissions — no create/update/delete."""
        from backend.rbac import Role, Permission, has_permission

        # Viewer CAN read
        assert has_permission(Role.VIEWER, Permission.PROJECT_READ)
        assert has_permission(Role.VIEWER, Permission.DEVICE_READ)
        assert has_permission(Role.VIEWER, Permission.CONNECTION_READ)
        assert has_permission(Role.VIEWER, Permission.REPORT_READ)
        assert has_permission(Role.VIEWER, Permission.ELEMENT_READ)
        assert has_permission(Role.VIEWER, Permission.CALCULATION_READ)
        assert has_permission(Role.VIEWER, Permission.HEALTH_READ)
        assert has_permission(Role.VIEWER, Permission.QOMN_READ)
        assert has_permission(Role.VIEWER, Permission.FACP_READ)
        assert has_permission(Role.VIEWER, Permission.WORKFLOW_READ)
        assert has_permission(Role.VIEWER, Permission.MONITOR_READ)

        # Viewer CANNOT create, update, or delete anything
        assert not has_permission(Role.VIEWER, Permission.PROJECT_CREATE)
        assert not has_permission(Role.VIEWER, Permission.PROJECT_UPDATE)
        assert not has_permission(Role.VIEWER, Permission.PROJECT_DELETE)
        assert not has_permission(Role.VIEWER, Permission.DEVICE_CREATE)
        assert not has_permission(Role.VIEWER, Permission.DEVICE_UPDATE)
        assert not has_permission(Role.VIEWER, Permission.DEVICE_DELETE)
        assert not has_permission(Role.VIEWER, Permission.CONNECTION_CREATE)
        assert not has_permission(Role.VIEWER, Permission.CONNECTION_UPDATE)
        assert not has_permission(Role.VIEWER, Permission.CONNECTION_DELETE)
        assert not has_permission(Role.VIEWER, Permission.ELEMENT_CREATE)
        assert not has_permission(Role.VIEWER, Permission.ELEMENT_UPDATE)
        assert not has_permission(Role.VIEWER, Permission.ELEMENT_DELETE)
        assert not has_permission(Role.VIEWER, Permission.REPORT_GENERATE)
        assert not has_permission(Role.VIEWER, Permission.REPORT_DELETE)
        assert not has_permission(Role.VIEWER, Permission.CALCULATION_EXECUTE)
        assert not has_permission(Role.VIEWER, Permission.QOMN_EXECUTE)
        assert not has_permission(Role.VIEWER, Permission.FACP_MANAGE)
        assert not has_permission(Role.VIEWER, Permission.WORKFLOW_MANAGE)
        assert not has_permission(Role.VIEWER, Permission.EXPORT_EXECUTE)
        assert not has_permission(Role.VIEWER, Permission.CONFLICT_RESOLVE)

        # Viewer CANNOT manage users or system config
        assert not has_permission(Role.VIEWER, Permission.USER_MANAGE)
        assert not has_permission(Role.VIEWER, Permission.SYSTEM_CONFIG)

    def test_viewer_is_strict_subset_of_engineer(self):
        """All viewer permissions should be a subset of engineer permissions."""
        from backend.rbac import Role, ROLE_PERMISSIONS

        viewer_perms = ROLE_PERMISSIONS[Role.VIEWER]
        engineer_perms = ROLE_PERMISSIONS[Role.ENGINEER]
        assert viewer_perms.issubset(engineer_perms)

    def test_engineer_is_strict_subset_of_admin(self):
        """All engineer permissions should be a subset of admin permissions."""
        from backend.rbac import Role, ROLE_PERMISSIONS

        engineer_perms = ROLE_PERMISSIONS[Role.ENGINEER]
        admin_perms = ROLE_PERMISSIONS[Role.ADMIN]
        assert engineer_perms.issubset(admin_perms)

    def test_get_role_permissions(self):
        """get_role_permissions should return the correct permission set."""
        from backend.rbac import Role, get_role_permissions, ROLE_PERMISSIONS

        for role in Role:
            assert get_role_permissions(role) == ROLE_PERMISSIONS[role]

    def test_unknown_role_returns_empty(self):
        """Unknown roles should return empty permissions."""
        from backend.rbac import get_role_permissions

        # Pass a string that's not a Role
        assert get_role_permissions("nonexistent") == set()


# ── Unit tests for API key management ───────────────────────────────────────


class TestAPIKeyManagement:
    """Test the API key management module."""

    def setup_method(self):
        """Set up a temporary keys file for each test."""
        self._tmpdir = tempfile.mkdtemp()
        self._keys_file = os.path.join(self._tmpdir, "api_keys.json")
        self._patcher = patch("backend.api_keys.KEYS_FILE", self._keys_file)
        self._patcher.start()

    def teardown_method(self):
        """Clean up the temporary keys file."""
        self._patcher.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_add_and_validate_key(self):
        """Adding a key should make it validatable."""
        from backend.api_keys import add_api_key, validate_api_key
        from backend.rbac import Role

        key_hash = add_api_key("test-key-123", Role.ENGINEER, "Test engineer key")
        info = validate_api_key("test-key-123")
        assert info is not None
        assert info.role == Role.ENGINEER
        assert info.description == "Test engineer key"
        assert info.key_hash == key_hash

    def test_invalid_key_returns_none(self):
        """Validating an invalid key should return None."""
        from backend.api_keys import validate_api_key

        info = validate_api_key("nonexistent-key")
        assert info is None

    def test_empty_key_returns_none(self):
        """Validating an empty key should return None."""
        from backend.api_keys import validate_api_key

        info = validate_api_key("")
        assert info is None

    def test_generate_api_key(self):
        """Generated keys should be validatable."""
        from backend.api_keys import generate_api_key, validate_api_key
        from backend.rbac import Role

        plaintext = generate_api_key(Role.VIEWER, "Auto-generated viewer")
        assert plaintext.startswith("fireai_")

        info = validate_api_key(plaintext)
        assert info is not None
        assert info.role == Role.VIEWER

    def test_list_api_keys(self):
        """list_api_keys should return key metadata without plaintext values."""
        from backend.api_keys import add_api_key, list_api_keys
        from backend.rbac import Role

        add_api_key("key1", Role.ADMIN, "Admin key")
        add_api_key("key2", Role.VIEWER, "Viewer key")

        keys = list_api_keys()
        assert len(keys) == 2
        roles = {k["role"] for k in keys}
        assert "admin" in roles
        assert "viewer" in roles
        # Key hashes should be present but not plaintext keys
        for k in keys:
            assert "key_hash" in k
            assert "key" not in k  # Never expose plaintext

    def test_delete_api_key(self):
        """Deleting a key should make it invalid."""
        from backend.api_keys import add_api_key, delete_api_key, validate_api_key
        from backend.rbac import Role

        key_hash = add_api_key("delete-me", Role.ENGINEER, "To delete")
        assert validate_api_key("delete-me") is not None

        deleted = delete_api_key(key_hash)
        assert deleted is True
        assert validate_api_key("delete-me") is None

    def test_delete_nonexistent_key(self):
        """Deleting a nonexistent key should return False."""
        from backend.api_keys import delete_api_key

        deleted = delete_api_key("nonexistent-hash")
        assert deleted is False

    def test_key_stored_as_hash(self):
        """Keys should be stored as SHA-256 hashes, never plaintext."""
        from backend.api_keys import _load_keys, add_api_key
        from backend.rbac import Role

        add_api_key("plaintext-key", Role.ADMIN, "Hash test")

        keys = _load_keys()
        expected_hash = hashlib.sha256("plaintext-key".encode()).hexdigest()
        assert expected_hash in keys
        # The plaintext key should NOT appear in the stored data
        stored_data = json.dumps(keys)
        assert "plaintext-key" not in stored_data

    def test_update_api_key_role(self):
        """Updating a key's role should change its role."""
        from backend.api_keys import add_api_key, update_api_key_role, validate_api_key
        from backend.rbac import Role

        key_hash = add_api_key("role-change-key", Role.VIEWER, "Role change test")
        info = validate_api_key("role-change-key")
        assert info.role == Role.VIEWER

        updated = update_api_key_role(key_hash, Role.ENGINEER)
        assert updated is True

        info = validate_api_key("role-change-key")
        assert info.role == Role.ENGINEER


# ── Integration tests for auth dependency ────────────────────────────────────


class TestAuthDependency:
    """Test the FastAPI permission checking dependency."""

    def _create_test_app(self):
        """Create a minimal FastAPI app with RBAC dependency for testing."""
        from backend.auth import require_permission, get_current_role
        from backend.rbac import Permission, Role

        app = FastAPI()

        @app.get("/public")
        async def public_endpoint():
            return {"message": "public"}

        @app.get("/read-only", dependencies=[Depends(require_permission(Permission.PROJECT_READ))])
        async def read_endpoint():
            return {"message": "read"}

        @app.post("/write", dependencies=[Depends(require_permission(Permission.PROJECT_CREATE))])
        async def write_endpoint():
            return {"message": "write"}

        @app.get("/admin-only", dependencies=[Depends(require_permission(Permission.USER_MANAGE))])
        async def admin_endpoint():
            return {"message": "admin"}

        return app

    def test_viewer_can_read(self):
        """Viewer should be able to access read endpoints."""
        from backend.rbac import Role
        app = self._create_test_app()
        client = TestClient(app)

        # Simulate viewer role on request.state
        response = client.get("/read-only", headers={"X-Test-Role": "viewer"})
        # Note: Without middleware setting the role, it defaults to VIEWER
        # which has PROJECT_READ permission
        assert response.status_code == 200

    def test_viewer_cannot_write(self):
        """Viewer should get 403 on write endpoints."""
        app = self._create_test_app()
        client = TestClient(app)

        # Default role is VIEWER (no middleware setting it)
        response = client.post("/write")
        assert response.status_code == 403
        assert "Permission denied" in response.json()["detail"]

    def test_viewer_cannot_access_admin(self):
        """Viewer should get 403 on admin-only endpoints."""
        app = self._create_test_app()
        client = TestClient(app)

        response = client.get("/admin-only")
        assert response.status_code == 403

    def test_admin_can_access_all(self):
        """Admin should be able to access all endpoints."""
        from backend.rbac import Role, Permission
        from backend.auth import require_permission
        app = self._create_test_app()
        client = TestClient(app)

        # We need to set the role via a middleware or directly
        # For testing, we'll use a custom middleware approach
        from starlette.middleware.base import BaseHTTPMiddleware

        class SetRoleMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                role_header = request.headers.get("X-Test-Role", "viewer")
                request.state.fireai_role = Role(role_header)
                response = await call_next(request)
                return response

        app_with_middleware = FastAPI()
        app_with_middleware.add_middleware(SetRoleMiddleware)

        @app_with_middleware.get("/read", dependencies=[Depends(require_permission(Permission.PROJECT_READ))])
        async def read_ep():
            return {"ok": True}

        @app_with_middleware.post("/write", dependencies=[Depends(require_permission(Permission.PROJECT_CREATE))])
        async def write_ep():
            return {"ok": True}

        @app_with_middleware.get("/admin", dependencies=[Depends(require_permission(Permission.USER_MANAGE))])
        async def admin_ep():
            return {"ok": True}

        client = TestClient(app_with_middleware)

        # Admin can do everything
        assert client.get("/read", headers={"X-Test-Role": "admin"}).status_code == 200
        assert client.post("/write", headers={"X-Test-Role": "admin"}).status_code == 200
        assert client.get("/admin", headers={"X-Test-Role": "admin"}).status_code == 200

        # Engineer can read and write but not admin
        assert client.get("/read", headers={"X-Test-Role": "engineer"}).status_code == 200
        assert client.post("/write", headers={"X-Test-Role": "engineer"}).status_code == 200
        assert client.get("/admin", headers={"X-Test-Role": "engineer"}).status_code == 403

        # Viewer can only read
        assert client.get("/read", headers={"X-Test-Role": "viewer"}).status_code == 200
        assert client.post("/write", headers={"X-Test-Role": "viewer"}).status_code == 403
        assert client.get("/admin", headers={"X-Test-Role": "viewer"}).status_code == 403

    def test_permission_denied_returns_403(self):
        """Permission denied should return HTTP 403 with descriptive message."""
        app = self._create_test_app()
        client = TestClient(app)

        response = client.post("/write")
        assert response.status_code == 403
        detail = response.json()["detail"]
        assert "project:create" in detail
        assert "viewer" in detail.lower()


# ── Import validation test ──────────────────────────────────────────────────


class TestBackendImports:
    """Verify that all RBAC modules can be imported successfully."""

    def test_import_rbac(self):
        """backend.rbac should be importable."""
        import backend.rbac
        assert hasattr(backend.rbac, "Role")
        assert hasattr(backend.rbac, "Permission")
        assert hasattr(backend.rbac, "has_permission")

    def test_import_api_keys(self):
        """backend.api_keys should be importable."""
        import backend.api_keys
        assert hasattr(backend.api_keys, "validate_api_key")
        assert hasattr(backend.api_keys, "generate_api_key")
        assert hasattr(backend.api_keys, "list_api_keys")

    def test_import_auth(self):
        """backend.auth should be importable."""
        import backend.auth
        assert hasattr(backend.auth, "get_current_role")
        assert hasattr(backend.auth, "require_permission")
