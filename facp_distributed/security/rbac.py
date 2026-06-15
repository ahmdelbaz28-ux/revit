"""
RBAC System for Distributed FACP System
"""
import time
from enum import Enum
from typing import Any, Dict, List, Optional


class Role(Enum):
    """Predefined roles in the distributed system"""
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"
    SYSTEM = "system"


class Permission(Enum):
    """Predefined permissions in the distributed system"""
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    ADMIN = "admin"
    ENGINE_ACCESS = "engine_access"
    CLIENT_ACCESS = "client_access"
    ORCHESTRATOR_ACCESS = "orchestrator_access"


class RBACEngine:
    """
    Role-Based Access Control Engine for distributed system
    """
    def __init__(self):
        self.roles = {}
        self.permissions = {}
        self.role_hierarchy = {}
        self.user_roles = {}
        self.resource_permissions = {}
        self.distributed_cache = {}  # For sharing RBAC state across nodes

        # Initialize default roles and permissions
        self._initialize_defaults()

    def _initialize_defaults(self):
        """Initialize default roles and their permissions"""
        # Define default role permissions
        default_role_perms = {
            Role.VIEWER.value: [Permission.READ],
            Role.OPERATOR.value: [Permission.READ, Permission.WRITE, Permission.EXECUTE],
            Role.ADMIN.value: [Permission.READ, Permission.WRITE, Permission.EXECUTE, Permission.ADMIN,
                              Permission.ENGINE_ACCESS, Permission.CLIENT_ACCESS, Permission.ORCHESTRATOR_ACCESS],
            Role.SYSTEM.value: [Permission.READ, Permission.WRITE, Permission.EXECUTE, Permission.ADMIN,
                               Permission.ENGINE_ACCESS, Permission.CLIENT_ACCESS, Permission.ORCHESTRATOR_ACCESS]
        }

        for role, perms in default_role_perms.items():
            self.roles[role] = [p.value for p in perms]

        # Define role hierarchy (lower number = lower privilege)
        self.role_hierarchy = {
            Role.VIEWER.value: 0,
            Role.OPERATOR.value: 1,
            Role.ADMIN.value: 2,
            Role.SYSTEM.value: 3
        }

    def create_role(self, role_name: str, permissions: List[str]):
        """Create a new role with specified permissions"""
        self.roles[role_name] = permissions

    def assign_role_to_user(self, user_id: str, role: str, expires_at: Optional[float] = None, node_id: str = None):
        """Assign a role to a user with optional node context"""
        if role not in self.roles:
            raise ValueError(f"Role '{role}' does not exist")

        if user_id not in self.user_roles:
            self.user_roles[user_id] = []

        # Check if role is already assigned
        existing_assignment = next((r for r in self.user_roles[user_id] if r['role'] == role and r.get('node_id') == node_id), None)
        if existing_assignment:
            existing_assignment['expires_at'] = expires_at
        else:
            assignment = {
                'role': role,
                'assigned_at': time.time(),
                'expires_at': expires_at,
                'node_id': node_id  # Assign role to specific node if specified
            }
            self.user_roles[user_id].append(assignment)

    def remove_role_from_user(self, user_id: str, role: str, node_id: str = None):
        """Remove a role from a user with optional node context"""
        if user_id in self.user_roles:
            if node_id:
                # Remove role only for specific node
                self.user_roles[user_id] = [
                    r for r in self.user_roles[user_id]
                    if not (r['role'] == role and r.get('node_id') == node_id)
                ]
            else:
                # Remove role for all nodes
                self.user_roles[user_id] = [r for r in self.user_roles[user_id] if r['role'] != role]

    def get_user_permissions(self, user_id: str, node_context: str = None) -> List[str]:
        """Get permissions for a user based on their roles in specific node context"""
        if user_id not in self.user_roles:
            return []

        # Filter roles by node context if specified
        active_roles = []
        current_time = time.time()

        for assignment in self.user_roles[user_id]:
            # Check if assignment is for specific node or all nodes
            node_matches = (assignment.get('node_id') is None or
                           assignment.get('node_id') == node_context)

            # Check if role hasn't expired
            not_expired = (assignment['expires_at'] is None or
                          assignment['expires_at'] > current_time)

            if node_matches and not_expired:
                active_roles.append(assignment['role'])

        permissions = set()
        for role in active_roles:
            if role in self.roles:
                permissions.update(self.roles[role])

        return list(permissions)

    def has_permission(self, user_id: str, required_permission: str, node_context: str = None) -> bool:
        """Check if a user has a specific permission in node context"""
        user_permissions = self.get_user_permissions(user_id, node_context)
        return required_permission in user_permissions

    def has_role(self, user_id: str, required_role: str, node_context: str = None) -> bool:
        """Check if a user has a specific role in node context"""
        if user_id not in self.user_roles:
            return False

        current_time = time.time()
        for assignment in self.user_roles[user_id]:
            # Check if role matches and is in correct context
            role_matches = assignment['role'] == required_role
            node_matches = (assignment.get('node_id') is None or
                           assignment.get('node_id') == node_context)
            not_expired = (assignment['expires_at'] is None or
                          assignment['expires_at'] > current_time)

            if role_matches and node_matches and not_expired:
                return True

        return False

    def is_authorized(self, user_id: str, required_permissions: List[str], node_context: str = None) -> bool:
        """Check if user has all required permissions in node context"""
        user_permissions = set(self.get_user_permissions(user_id, node_context))
        required_set = set(required_permissions)
        return required_set.issubset(user_permissions)

    def get_role_hierarchy_level(self, role: str) -> Optional[int]:
        """Get the hierarchy level of a role"""
        return self.role_hierarchy.get(role)

    def distribute_state(self, target_nodes: list):
        """
        Distribute RBAC state to other nodes in the cluster
        """
        rbac_state = {
            "roles": self.roles,
            "role_hierarchy": self.role_hierarchy,
            "user_roles": self.user_roles,
            "timestamp": time.time()
        }

        # In a real implementation, this would send the state to other nodes
        for node in target_nodes:
            self.distributed_cache[node] = rbac_state

    def sync_with_cluster(self, cluster_rbac_state: Dict[str, Any]):
        """
        Sync RBAC state with cluster
        """
        # Merge cluster state with local state
        cluster_roles = cluster_rbac_state.get("roles", {})
        cluster_user_roles = cluster_rbac_state.get("user_roles", {})
        cluster_hierarchy = cluster_rbac_state.get("role_hierarchy", {})

        # Update roles
        for role, perms in cluster_roles.items():
            if role not in self.roles:
                self.roles[role] = perms

        # Update role hierarchy
        for role, level in cluster_hierarchy.items():
            if role not in self.role_hierarchy:
                self.role_hierarchy[role] = level

        # Update user roles (be careful about conflicts)
        for user_id, assignments in cluster_user_roles.items():
            if user_id not in self.user_roles:
                self.user_roles[user_id] = assignments
            else:
                # Merge assignments, preferring newer ones
                local_assignments = {f"{a['role']}_{a.get('node_id', 'all')}": a for a in self.user_roles[user_id]}
                for assignment in assignments:
                    key = f"{assignment['role']}_{assignment.get('node_id', 'all')}"
                    if key not in local_assignments or assignment['assigned_at'] > local_assignments[key]['assigned_at']:
                        local_assignments[key] = assignment

                self.user_roles[user_id] = list(local_assignments.values())


class PermissionChecker:
    """
    Permission checking utility for distributed system
    """
    def __init__(self, rbac_engine: RBACEngine):
        self.rbac_engine = rbac_engine

    def check_method_access(self, user_id: str, method: str, node_context: str = None) -> tuple[bool, str]:
        """
        Check if user can access a specific method in node context
        :param user_id: User ID
        :param method: Method name (e.g., "engine.calculate", "orchestrator.route")
        :param node_context: Node where operation is happening
        :return: (is_allowed, reason)
        """
        # Define method-to-permission mappings
        method_permissions = {
            "engine.*": ["engine_access"],
            "engine.calculate": ["execute", "engine_access"],
            "engine.validate": ["execute", "engine_access"],
            "engine.transform": ["execute", "engine_access"],
            "orchestrator.*": ["orchestrator_access"],
            "orchestrator.route": ["orchestrator_access"],
            "orchestrator.plan": ["orchestrator_access"],
            "client.*": ["client_access"],
            "admin.*": ["admin"],
            "system.*": ["admin"],
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

        # Check if user has required permissions in node context
        if self.rbac_engine.is_authorized(user_id, required_permissions, node_context):
            return True, "Access granted"
        else:
            return False, f"Insufficient permissions. Required: {required_permissions}"

    def check_resource_access(self, user_id: str, resource: str, action: str, node_context: str = None) -> tuple[bool, str]:
        """
        Check if user can perform an action on a resource in node context
        :param user_id: User ID
        :param resource: Resource identifier
        :param action: Action (read/write/execute)
        :param node_context: Node where operation is happening
        :return: (is_allowed, reason)
        """
        required_permission = f"{action}"

        if self.rbac_engine.has_permission(user_id, required_permission, node_context):
            return True, "Access granted"
        else:
            return False, f"Insufficient permissions for {action} on {resource}"

    def get_user_capabilities(self, user_id: str, node_context: str = None) -> Dict[str, Any]:
        """Get all capabilities for a user in node context"""
        permissions = self.rbac_engine.get_user_permissions(user_id, node_context)
        roles = []

        if user_id in self.rbac_engine.user_roles:
            current_time = time.time()
            for assignment in self.rbac_engine.user_roles[user_id]:
                # Check if role is active in the specified context
                node_matches = (assignment.get('node_id') is None or
                               assignment.get('node_id') == node_context)
                not_expired = (assignment['expires_at'] is None or
                              assignment['expires_at'] > current_time)

                if node_matches and not_expired:
                    roles.append(assignment['role'])

        return {
            "user_id": user_id,
            "roles": roles,
            "permissions": permissions,
            "node_context": node_context,
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
        elif "orchestrator_access" in perm_set:
            capabilities.append("orchestrator_access")

        if "execute" in perm_set:
            capabilities.append("task_execution")

        if len(perm_set.intersection({"read", "write", "execute"})) > 0:
            capabilities.append("basic_operations")

        return capabilities

    def validate_cross_node_access(self, requesting_user: str, target_node: str,
                                 action: str, resource: str) -> tuple[bool, str]:
        """
        Validate if a user can access resources on a different node
        """
        # Check if user has permission to access the target node type
        node_type = target_node.split('_')[0] if '_' in target_node else target_node

        required_perm = f"{node_type}_access" if node_type in ['engine', 'client', 'orchestrator'] else "admin"

        if self.rbac_engine.has_permission(requesting_user, required_perm):
            # User has basic access to node type, now check specific resource/action
            resource_perm = f"{action}"
            if self.rbac_engine.has_permission(requesting_user, resource_perm):
                return True, "Cross-node access granted"
            else:
                return False, f"Insufficient permissions for {action} on {resource}"
        else:
            return False, f"User does not have access to {node_type} nodes"
