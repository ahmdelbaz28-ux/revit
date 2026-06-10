"""
SGL Authorization Engine - RBAC Subsystem
"""

from typing import Dict, List, Optional
from ..models import ExecutionRequest, Role
from ..exceptions import GovernanceException


class AuthorizationEngine:
    """
    Authorization Engine - Role-Based Access Control (RBAC)
    Every request must include role, every action must map to allowed role capabilities
    """
    
    def __init__(self):
        # Define role capabilities mapping
        self.role_capabilities = {
            Role.ADMIN: [
                "execute_any", "modify_policy", "access_all_data", 
                "manage_users", "configure_system", "bypass_limits"
            ],
            Role.OPERATOR: [
                "execute_standard", "access_operational_data", 
                "view_logs", "manage_own_tasks"
            ],
            Role.VIEWER: [
                "read_only", "view_status", "access_public_data"
            ],
            Role.SYSTEM_AGENT: [
                "execute_internal", "access_system_data", 
                "perform_maintenance", "internal_communication"
            ]
        }
        
        # Define action requirements
        self.action_requirements = {
            "execute_calculation": [Role.ADMIN, Role.OPERATOR, Role.SYSTEM_AGENT],
            "execute_transformation": [Role.ADMIN, Role.OPERATOR, Role.SYSTEM_AGENT],
            "execute_validation": [Role.ADMIN, Role.OPERATOR, Role.SYSTEM_AGENT],
            "execute_optimization": [Role.ADMIN, Role.OPERATOR, Role.SYSTEM_AGENT],
            "access_admin_panel": [Role.ADMIN],
            "modify_user_permissions": [Role.ADMIN],
            "view_audit_logs": [Role.ADMIN, Role.OPERATOR],
            "read_only_access": [Role.VIEWER, Role.ADMIN, Role.OPERATOR, Role.SYSTEM_AGENT]
        }
    
    def authorize_request(self, request: ExecutionRequest, required_action: Optional[str] = None) -> bool:
        """
        Authorize the execution request based on role and required action
        
        Args:
            request: The execution request to authorize
            required_action: The specific action being requested (optional)
            
        Returns:
            True if authorized, raises exception if not
        """
        # Verify the role is valid
        if request.role not in self.role_capabilities:
            raise GovernanceException(f"Invalid role: {request.role}")
        
        # If no specific action is required, just check if the role exists
        if not required_action:
            return True
        
        # Check if the role has the required capability
        required_roles = self.action_requirements.get(required_action, [])
        
        if request.role not in required_roles:
            raise GovernanceException(
                f"Role {request.role} does not have permission for action '{required_action}'. "
                f"Required roles: {[role.value for role in required_roles]}"
            )
        
        # Additional checks based on risk level and role
        if request.risk_level == "critical" and request.role not in [Role.ADMIN, Role.SYSTEM_AGENT]:
            raise GovernanceException(
                f"Critical risk operations require admin or system agent role, got {request.role}"
            )
        
        return True
    
    def get_role_capabilities(self, role: Role) -> List[str]:
        """Get the capabilities for a given role"""
        return self.role_capabilities.get(role, [])
    
    def validate_role_assignment(self, user_id: str, role: Role) -> bool:
        """
        Validate that a user can be assigned to a particular role
        This would typically integrate with user management system
        """
        # For now, just validate the role is known
        return role in self.role_capabilities