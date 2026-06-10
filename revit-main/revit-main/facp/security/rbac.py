"""
FACP RBAC (Role-Based Access Control) System
"""
from typing import Dict, List, Any, Optional
from enum import Enum
import time


class Role(Enum):
    """Predefined roles in the system"""
    GUEST = "guest"
    ENGINEER = "engineer"
    ADMIN = "admin"
    AUDITOR = "auditor"
    SYSTEM = "system"


class Permission(Enum):
    """Predefined permissions in the system"""
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    ADMIN = "admin"
    ENGINE_ACCESS = "engine_access"
    AUDIT = "audit"


class RBACEngine:
    """
    Role-Based Access Control Engine
    """
    def __init__(self):
        self.roles = {}
        self.permissions = {}
        self.role_hierarchy = {}
        self.user_roles = {}
        self.resource_permissions = {}

        # Initialize default roles and permissions
        self._initialize_defaults()

    def _initialize_defaults(self):
        """Initialize default roles and their permissions"""
        # Define default role permissions
        default_role_perms = {
            Role.GUEST.value: [Permission.READ],
            Role.ENGINEER.value: [Permission.READ, Permission.WRITE, Permission.EXECUTE],
            Role.ADMIN.value: [Permission.READ, Permission.WRITE, Permission.EXECUTE, Permission.ADMIN, Permission.ENGINE_ACCESS],
            Role.AUDITOR.value: [Permission.READ, Permission.AUDIT],
            Role.SYSTEM.value: [Permission.READ, Permission.WRITE, Permission.EXECUTE, Permission.ADMIN, Permission.ENGINE_ACCESS]
        }

        for role, perms in default_role_perms.items():
            self.roles[role] = [p.value for p in perms]

        # Define role hierarchy (lower number = lower privilege)
        self.role_hierarchy = {
            Role.GUEST.value: 0,
            Role.ENGINEER.value: 1,
            Role.AUDITOR.value: 2,
            Role.ADMIN.value: 3,
            Role.SYSTEM.value: 4
        }

    def create_role(self, role_name: str, permissions: List[str]):
        """Create a new role with specified permissions"""
        self.roles[role_name] = permissions

    def assign_role_to_user(self, user_id: str, role: str, expires_at: Optional[float] = None):
        """Assign a role to a user"""
        if role not in self.roles:
            raise ValueError(f"Role '{role}' does not exist")
        
        if user_id not in self.user_roles:
            self.user_roles[user_id] = []
        
        # Check if role is already assigned
        existing_assignment = next((r for r in self.user_roles[user_id] if r['role'] == role), None)
        if existing_assignment:
            existing_assignment['expires_at'] = expires_at
        else:
            self.user_roles[user_id].append({
                'role': role,
                'assigned_at': time.time(),
                'expires_at': expires_at
            })

    def remove_role_from_user(self, user_id: str, role: str):
        """Remove a role from a user"""
        if user_id in self.user_roles:
            self.user_roles[user_id] = [r for r in self.user_roles[user_id] if r['role'] != role]

    def get_user_permissions(self, user_id: str) -> List[str]:
        """Get all permissions for a user based on their roles"""
        if user_id not in self.user_roles:
            return []

        # Filter out expired roles
        current_time = time.time()
        active_roles = [
            r['role'] for r in self.user_roles[user_id] 
            if r['expires_at'] is None or r['expires_at'] > current_time
        ]

        permissions = set()
        for role in active_roles:
            if role in self.roles:
                permissions.update(self.roles[role])

        return list(permissions)

    def has_permission(self, user_id: str, required_permission: str) -> bool:
        """Check if a user has a specific permission"""
        user_permissions = self.get_user_permissions(user_id)
        return required_permission in user_permissions

    def has_role(self, user_id: str, required_role: str) -> bool:
        """Check if a user has a specific role"""
        if user_id not in self.user_roles:
            return False

        current_time = time.time()
        active_roles = [
            r['role'] for r in self.user_roles[user_id] 
            if r['expires_at'] is None or r['expires_at'] > current_time
        ]

        return required_role in active_roles

    def is_authorized(self, user_id: str, required_permissions: List[str]) -> bool:
        """Check if user has all required permissions"""
        user_permissions = set(self.get_user_permissions(user_id))
        required_set = set(required_permissions)
        return required_set.issubset(user_permissions)

    def get_role_hierarchy_level(self, role: str) -> Optional[int]:
        """Get the hierarchy level of a role"""
        return self.role_hierarchy.get(role)


class PermissionChecker:
    """
    Permission checking utility
    """
    def __init__(self, rbac_engine: RBACEngine):
        self.rbac_engine = rbac_engine

    def check_method_access(self, user_id: str, method: str) -> tuple[bool, str]:
        """
        Check if user can access a specific method
        :param user_id: User ID
        :param method: Method name (e.g., "engine.calculate", "orchestrator.plan")
        :return: (is_allowed, reason)
        """
        # Define method-to-permission mappings
        method_permissions = {
            "engine.*": ["engine_access"],
            "engine.calculate": ["execute", "engine_access"],
            "engine.validate": ["execute", "engine_access"],
            "engine.transform": ["execute", "engine_access"],
            "orchestrator.*": ["execute"],
            "orchestrator.plan": ["execute"],
            "orchestrator.route": ["execute"],
            "admin.*": ["admin"],
            "system.*": ["admin"],
            "audit.*": ["audit"]
        }

        # Find matching permissions for the method
        required_permissions = []
        
        # Check for exact match first
        if method in method_permissions:
            required_permissions = method_permissions[method]
        else:
            # Check for wildcard matches
            for pattern, perms in method_permissions.items():
                if pattern.endswith('*') and method.startswith(pattern[:-1]):
                    required_permissions = perms
                    break

        if not required_permissions:
            # Default to requiring execute permission for unknown methods
            required_permissions = ["execute"]

        # Check if user has required permissions
        if self.rbac_engine.is_authorized(user_id, required_permissions):
            return True, "Access granted"
        else:
            return False, f"Insufficient permissions. Required: {required_permissions}"

    def check_resource_access(self, user_id: str, resource: str, action: str) -> tuple[bool, str]:
        """
        Check if user can perform an action on a resource
        :param user_id: User ID
        :param resource: Resource identifier
        :param action: Action (read/write/execute)
        :return: (is_allowed, reason)
        """
        required_permission = f"{action}"
        
        if self.rbac_engine.has_permission(user_id, required_permission):
            return True, "Access granted"
        else:
            return False, f"Insufficient permissions for {action} on {resource}"

    def get_user_capabilities(self, user_id: str) -> Dict[str, Any]:
        """Get all capabilities for a user"""
        permissions = self.rbac_engine.get_user_permissions(user_id)
        roles = []
        
        if user_id in self.rbac_engine.user_roles:
            current_time = time.time()
            roles = [
                r['role'] for r in self.rbac_engine.user_roles[user_id] 
                if r['expires_at'] is None or r['expires_at'] > current_time
            ]

        return {
            "user_id": user_id,
            "roles": roles,
            "permissions": permissions,
            "capabilities": self._derive_capabilities(permissions)
        }

    def _derive_capabilities(self, permissions: List[str]) -> List[str]:
        """Derive high-level capabilities from permissions"""
        capabilities = []
        
        perm_set = set(permissions)
        
        if "admin" in perm_set:
            capabilities.append("full_admin")
        elif "engine_access" in perm_set:
            capabilities.append("engine_access")
        
        if "execute" in perm_set:
            capabilities.append("task_execution")
        
        if "audit" in perm_set:
            capabilities.append("audit_access")
        
        if len(perm_set.intersection({"read", "write", "execute"})) > 0:
            capabilities.append("basic_operations")
        
        return capabilities