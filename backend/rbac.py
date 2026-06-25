"""Role-Based Access Control for FireAI Digital Twin Platform.

Three-role RBAC system:
  - admin:    Full access to everything (CRUD all resources, manage users, system config)
  - engineer: Can create/edit/delete projects, devices, connections, run calculations,
              generate reports (but cannot manage users or system config)
  - viewer:   Read-only access to projects, devices, connections, reports
              (cannot create/edit/delete anything)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Role(str, Enum):
    """User roles in the FireAI platform."""

    ADMIN = "admin"
    ENGINEER = "engineer"
    VIEWER = "viewer"


# Permission definitions
class Permission(str, Enum):
    """Granular permissions for the FireAI platform."""

    # Project permissions
    PROJECT_READ = "project:read"
    PROJECT_CREATE = "project:create"
    PROJECT_UPDATE = "project:update"
    PROJECT_DELETE = "project:delete"
    # Device permissions
    DEVICE_READ = "device:read"
    DEVICE_CREATE = "device:create"
    DEVICE_UPDATE = "device:update"
    DEVICE_DELETE = "device:delete"
    # Connection permissions
    CONNECTION_READ = "connection:read"
    CONNECTION_CREATE = "connection:create"
    CONNECTION_UPDATE = "connection:update"
    CONNECTION_DELETE = "connection:delete"
    # Engineering calculation permissions
    CALCULATION_READ = "calculation:read"
    CALCULATION_EXECUTE = "calculation:execute"
    # Report permissions
    REPORT_READ = "report:read"
    REPORT_GENERATE = "report:generate"
    REPORT_DELETE = "report:delete"
    # Export permissions
    EXPORT_READ = "export:read"
    EXPORT_EXECUTE = "export:execute"
    # Element permissions (UDM)
    ELEMENT_READ = "element:read"
    ELEMENT_CREATE = "element:create"
    ELEMENT_UPDATE = "element:update"
    ELEMENT_DELETE = "element:delete"
    # Conflict permissions
    CONFLICT_READ = "conflict:read"
    CONFLICT_RESOLVE = "conflict:resolve"
    # System permissions
    SYSTEM_CONFIG = "system:config"
    USER_MANAGE = "user:manage"
    MONITOR_READ = "monitor:read"
    HEALTH_READ = "health:read"
    # QOMN permissions
    QOMN_READ = "qomn:read"
    QOMN_EXECUTE = "qomn:execute"
    # FACP permissions
    FACP_READ = "facp:read"
    FACP_MANAGE = "facp:manage"
    # Workflow permissions
    WORKFLOW_READ = "workflow:read"
    WORKFLOW_MANAGE = "workflow:manage"


# Role-permission mapping
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.ADMIN: {
        # Admins have ALL permissions
        *Permission.__members__.values()
    },
    Role.ENGINEER: {
        Permission.PROJECT_READ,
        Permission.PROJECT_CREATE,
        Permission.PROJECT_UPDATE,
        Permission.PROJECT_DELETE,
        Permission.DEVICE_READ,
        Permission.DEVICE_CREATE,
        Permission.DEVICE_UPDATE,
        Permission.DEVICE_DELETE,
        Permission.CONNECTION_READ,
        Permission.CONNECTION_CREATE,
        Permission.CONNECTION_UPDATE,
        Permission.CONNECTION_DELETE,
        Permission.CALCULATION_READ,
        Permission.CALCULATION_EXECUTE,
        Permission.REPORT_READ,
        Permission.REPORT_GENERATE,
        Permission.REPORT_DELETE,
        Permission.EXPORT_READ,
        Permission.EXPORT_EXECUTE,
        Permission.ELEMENT_READ,
        Permission.ELEMENT_CREATE,
        Permission.ELEMENT_UPDATE,
        Permission.ELEMENT_DELETE,
        Permission.CONFLICT_READ,
        Permission.CONFLICT_RESOLVE,
        Permission.HEALTH_READ,
        Permission.QOMN_READ,
        Permission.QOMN_EXECUTE,
        Permission.FACP_READ,
        Permission.FACP_MANAGE,
        Permission.WORKFLOW_READ,
        Permission.WORKFLOW_MANAGE,
        Permission.MONITOR_READ,
    },
    Role.VIEWER: {
        Permission.PROJECT_READ,
        Permission.DEVICE_READ,
        Permission.CONNECTION_READ,
        Permission.CALCULATION_READ,
        Permission.REPORT_READ,
        Permission.EXPORT_READ,
        Permission.ELEMENT_READ,
        Permission.CONFLICT_READ,
        Permission.HEALTH_READ,
        Permission.QOMN_READ,
        Permission.FACP_READ,
        Permission.WORKFLOW_READ,
        Permission.MONITOR_READ,
    },
}


@dataclass
class APIKeyInfo:
    """Parsed API key information."""

    key_hash: str
    role: Role
    description: str


def has_permission(role: Role, permission: Permission) -> bool:
    """Check if a role has a specific permission."""
    return permission in ROLE_PERMISSIONS.get(role, set())


def get_role_permissions(role: Role) -> set[Permission]:
    """Get all permissions for a role."""
    return ROLE_PERMISSIONS.get(role, set())
